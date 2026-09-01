"""Quantitative, hardware-free runtime evidence for the visual showcase.

One fixture performs the real 10,704-frame ShowRuntime replay.  It captures
the contributions already rendered for composition, so stateful effects are
never called again to obtain Finale layers.  Legacy width-one twinkle uses
module RNG; replay explicitly saves, seeds and restores that state.  Thus the
determinism tested here is seed-controlled offline determinism, not a claim
that ShowRuntime's seed alone controls every legacy effect.
"""
from __future__ import annotations

import hashlib
import random
import copy
import colorsys
import math
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

import light_engine.show.compositor as compositor
from light_engine.config import Config
from light_engine.mapping import Layout, ZoneDef
from light_engine.models import AudioFeatures, DigitalStrip, EffectContext, PixelFrame, VideoFeatures
from light_engine.outputs.transform import OutputTransform
from light_engine.show import CueRenderJob, ShowRuntime, TargetCatalog, TargetResolver, black_base_frame, compose_frame, load_show
from light_engine.show.models import ColorSpec, EffectSpec
from light_engine.effects import create_effect

REPO = Path(__file__).resolve().parents[1]
SHOW = REPO / "config" / "acceptance" / "single-strip-visual-showcase-v2" / "show.yaml"
PROFILE = REPO / "config" / "profiles" / "rk3588-host-service.yaml"
TARGET, FPS, SEED = "strip_43", 30, 74043

@dataclass
class Audit:
    config: Config; layout: Layout; show: object; digest: str
    frames: dict[str, list[tuple[float, list[tuple[int,int,int]]]]]
    contributions: dict[float, tuple]; bases: dict[float, PixelFrame]; tail: list[list[tuple[int,int,int]]]
    trace: dict[str, list[tuple[EffectContext, PixelFrame, object]]]

def _fail(cue, t, group, actual, expected):
    return f"{cue} at {t:.3f}s group {group}: actual uint8={actual}; expected {expected}"

def _load():
    Config.reset(); config=Config.get_instance(PROFILE); layout=Layout.from_config(config)
    return config, layout, load_show(SHOW, TargetCatalog.from_layout(layout))

def _transform(config):
    return OutputTransform(global_brightness=config.get("system.smoothing.max_brightness"), gamma=config.get("system.smoothing.gamma"), power_limit=config.get("outputs.transform.power_limit", 5.0), per_zone_warm_bias=config.get("outputs.transform.per_zone_warm_bias", {}), per_zone_cool_bias=config.get("outputs.transform.per_zone_cool_bias", {}))

def _u8(frame): return next(s.to_uint8() for s in frame.strips if s.strip_id == TARGET)
def _active(pixels, threshold=4): return [i for i,p in enumerate(pixels) if max(p)>threshold]

class _TraceEffect:
    def __init__(self, inner, trace): self.inner, self.name, self.trace = inner, inner.name, trace
    def process(self, ctx):
        frame=self.inner.process(ctx)
        # Copy meaningful mutable state at this exact process call; never retain
        # an effect reference as purported historical evidence.
        state={key: copy.deepcopy(getattr(self.inner,key)) for key in ("_position","_phase","_positions","_last_steps","_last_target_tick","_strip_ticks","_pixels") if hasattr(self.inner,key)}
        self.trace.setdefault(str(ctx.mode_parameters.get("cue_id")),[]).append((ctx,frame,state)); return frame
    def reset(self): return self.inner.reset()

def _replay(*, capture=False, media=False):
    config, layout, show = _load(); state=random.getstate(); random.seed(SEED)
    original=compositor.compose_frame; captured={}
    def record(base, contributions):
        values=tuple(contributions); captured[base.timestamp]=values
        return original(base, values)
    if capture: compositor.compose_frame=record
    try:
        trace={}
        runtime=ShowRuntime.from_layout(show, layout, seed=SEED, effect_factory=lambda name: _TraceEffect(create_effect(name),trace)); transform=_transform(config); digest=hashlib.sha256(); frames={}; bases={}; tail=[]
        for i in range(int(show.duration*FPS)):
            t=i/FPS; base=black_base_frame(timestamp=t, sequence=i, analog_zones=layout.zones, digital_strips=layout.strips)
            audio=AudioFeatures(timestamp=t,rms=(i%7)/6,loudness=(i%5)/4,onset=float(i%11==0)) if media else None
            video=VideoFeatures(timestamp=t,average_rgb=((i%3)/2,.3,.7),dominant_rgb=(.9,.1,.4),brightness=.7,saturation=.8) if media else None
            frame=transform.apply_to_frame(runtime.render(EffectContext(timestamp=t,delta_time=1/FPS,sequence=i,audio_features=audio,video_features=video),base)); pixels=_u8(frame)
            digest.update(bytes(c for p in pixels for c in p))
            for strip in frame.strips:
                if strip.strip_id != TARGET: assert not any(c for p in strip.to_uint8() for c in p), _fail("scope",t,0,strip.to_uint8()[0],"other profile strips black")
            for cue in show.cues:
                if cue.start <= t < cue.end: frames.setdefault(cue.id,[]).append((t,pixels))
            if capture: bases[t]=base
            if i>=int((show.duration-2)*FPS): tail.append(pixels)
        return Audit(config,layout,show,digest.hexdigest(),frames,captured,bases,tail,trace)
    finally:
        compositor.compose_frame=original; random.setstate(state)

@pytest.fixture(scope="module")
def audit(): return _replay(capture=True)

@pytest.fixture(scope="module")
def replays(audit): return audit, _replay(), _replay(media=True)

def _mid(audit, cue): return audit.frames[cue][3:-3]

def test_full_30fps_runtime_is_deterministic_media_free_and_safe(audit, replays):
    primary, repeat, varying=replays
    for candidate, label in ((repeat,"same-seed"),(varying,"varying-feature")):
        if primary.digest != candidate.digest:
            for cue_id, frames in primary.frames.items():
                other=dict(candidate.frames.get(cue_id,()))
                for t, actual in frames:
                    expected=other.get(t)
                    if expected is not None and actual!=expected:
                        group=next(i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b)
                        raise AssertionError(_fail(cue_id,t,group,actual[group],f"{label} expected uint8={expected[group]}"))
            raise AssertionError(f"{label}: digest mismatch without a recoverable target frame")
    assert len(audit.tail)==60
    for i,pixels in enumerate(audit.tail): assert all(p==(0,0,0) for p in pixels), _fail("SAFE_black",354.8+i/FPS,0,pixels[0],"all groups black")

def test_each_family_has_real_quantized_motion_or_structure(audit):
    for v in "ABCD":
        # Use the luminance envelope rather than one colour channel: B is orange.
        b=[max(max(p) for p in px) for _,px in _mid(audit,f"FX_breath_{v}")]; assert max(b)-min(b)>35, f"FX_breath_{v}: cadence absent"
        wave=_mid(audit,f"FX_color_wave_{v}"); assert wave[0][1] != wave[-1][1], _fail(f"FX_color_wave_{v}",wave[-1][0],0,wave[-1][1][0],"native phase moves")
    seen=set()
    for v in "ABCD":
        for t,px in _mid(audit,f"FX_single_dot_{v}"):
            lit=_active(px); assert len(lit)==1, _fail(f"FX_single_dot_{v}",t,lit[0] if lit else 0,px,"one main dot with no tail"); seen.update(lit)
        t,px=_mid(audit,f"FX_chase_{v}")[20]; active=_active(px); assert any(b-a>1 for a,b in zip(active,active[1:])), _fail(f"FX_chase_{v}",t,0,px,"gaps")
        t,px=_mid(audit,f"FX_flowing_bands_{v}")[20]; assert all(max(px[i])==0 for i in range(1,20,2)), _fail(f"FX_flowing_bands_{v}",t,1,px[1],"one dark gap per two-group step")
    assert seen==set(range(20)), f"single_dot did not cover groups {set(range(20))-seen}"

def test_comet_wipe_twinkle_heat_history_noise_evidence(audit):
    # Tail length is expressed as strip fraction: A/B heads have 3/4 tail groups.
    for v,limit in zip("ABCD",(4,5,8,9)):
        counts=[len(_active(px)) for _,px in _mid(audit,f"FX_comet_{v}")]; assert 2<=max(counts)<=limit, f"FX_comet_{v}: active coverage {min(counts)}..{max(counts)}"
    for cue in [c for c in audit.show.cues if c.id.startswith("FX_color_wipe_")]:
        complete=[t for t,px in audit.frames[cue.id] if t<cue.end-cue.transition.fade_out and len(_active(px))==20]
        runs=[]; current=[]
        for t in complete:
            if current and t-current[-1]>1/FPS+1e-9: runs.append(current); current=[]
            current.append(t)
        if current: runs.append(current)
        assert runs and max(len(run) for run in runs)>=9, _fail(cue.id,cue.start,0,(),"nine contiguous complete frames before .1s fade")
    counts=[len(_active(px)) for _,px in _mid(audit,"FX_twinkle_A")]; assert 0<max(counts)<10 and len(set(counts))>2, "twinkle: local births and decay required"
    for variant in "ABCD":
        heat=_mid(audit,f"FX_heat_fire_{variant}")
        assert any(px!=heat[0][1] for _,px in heat[1:]) and any(max(px[group])>4 for _,px in heat for group in range(3,20)), f"FX_heat_fire_{variant}: formal window lacks visible propagation beyond group 2"
    for v in "ABCD":
        frames=_mid(audit,f"FX_history_stream_{v}"); t,px=frames[-10]; assert len({p for p in px if max(p)>4})>=2, _fail(f"FX_history_stream_{v}",t,0,px[0],"retained ordered native-timeline colours")

def test_finale_decomposition_uses_captured_contributions_once(audit):
    transform=_transform(audit.config); changed={name:0 for name in ("FIN_noise_S1","FIN_noise_S2","FIN_noise_S3","FIN_twinkle","FIN_comet_S3","FIN_comet_S4")}
    actual_by_time={t:pixels for frames in audit.frames.values() for t,pixels in frames}
    for index in range(9804,10644):
        t=index/FPS; contributions=audit.contributions[t]; base=audit.bases[t]
        manual=[[0.,0.,0.] for _ in range(20)]
        for item in sorted(contributions,key=lambda c:(c.priority,c.declaration_index)):
            pixels=item.digital[0].pixels
            for group,incoming in enumerate(pixels):
                if incoming is None: continue
                before=manual[group]
                manual[group]=[before[channel]*(1-item.weight)+incoming[channel]*item.weight for channel in range(3)] if item.blend=="replace" else [before[channel]+incoming[channel]*item.weight for channel in range(3)]
                assert all(0<=channel<=1 for channel in manual[group]), _fail(item.cue_id,t,group,DigitalStrip(TARGET,1,transform.apply_to_pixels([tuple(manual[group])])).to_uint8()[0],"unclamped intermediate RGB in [0,1]")
        composed=compose_frame(base,contributions); expected=[tuple(pixel) for pixel in manual]
        actual=next(strip.pixels for strip in composed.strips if strip.strip_id==TARGET)
        for group,(actual_pixel,expected_pixel) in enumerate(zip(actual,expected)):
            assert actual_pixel==pytest.approx(expected_pixel,abs=1e-12), _fail("Finale",t,group,DigitalStrip(TARGET,1,transform.apply_to_pixels([actual_pixel])).to_uint8()[0],"manual ordered composition")
        quantized=DigitalStrip(TARGET,20,transform.apply_to_pixels(actual)).to_uint8()
        recorded=actual_by_time[t]
        assert quantized==recorded, _fail("Finale",t,0,recorded[0],f"production uint8 {quantized[0]}")
        for item in contributions:
            without=_u8(transform.apply_to_frame(compose_frame(base,[c for c in contributions if c is not item])))
            if without!=quantized: changed[item.cue_id]+=1
        if 10554<=index<=10643:
            assert {c.cue_id for c in contributions}=={"FIN_noise_S3","FIN_twinkle","FIN_comet_S4"}
            expected_weight=(354.8-t)/3
            assert all(c.weight==pytest.approx(expected_weight,abs=1e-9) for c in contributions), f"Finale {t:.3f}: fade weights {[c.weight for c in contributions]}, expected {expected_weight}"
    assert all(count>0 for count in changed.values()), f"Finale contribution quantized differences {changed}"

def test_independent_same_identity_controls_measure_common_motion(audit):
    resolver=TargetResolver((),(ZoneDef(id=TARGET,pixel_count=20),))
    for family in ("single_dot","chase","comet","color_wipe","flowing_bands","history_stream","coherent_noise_field","heat_fire"):
        cue=next(c for c in audit.show.cues if c.id==f"FX_{family}_A")
        fast=replace(cue,effect=EffectSpec(mode="fixed",id=cue.effect.id,speed=9.5,intensity=cue.effect.intensity,params=cue.effect.params))
        low,high=CueRenderJob(cue,0,resolver,cue_seed=SEED),CueRenderJob(fast,0,resolver,cue_seed=SEED)
        low_out=high_out=None
        for i in range(31):
            ctx=EffectContext(timestamp=cue.start+i/FPS,delta_time=1/FPS,sequence=i); low_out=low.render(ctx); high_out=high.render(ctx)
        assert high._motion_clock.current.motion_time>low._motion_clock.current.motion_time, f"{family}: independent same-id high-speed control did not advance farther"
        assert low.effect is not high.effect, f"{family}: controls unexpectedly shared state"
        assert low_out.digital[0].pixels != high_out.digital[0].pixels, f"{family}: emitted output ignored independent speed control"

def test_independent_controls_change_effect_outputs_for_breath_wave_and_twinkle(audit):
    resolver=TargetResolver((),(ZoneDef(id=TARGET,pixel_count=20),))
    def render(cue, seconds=1.0):
        job=CueRenderJob(cue,0,resolver,cue_seed=SEED); out=None
        for i in range(int(seconds*FPS)+1): out=job.render(EffectContext(timestamp=cue.start+i/FPS,delta_time=1/FPS,sequence=i))
        return out.digital[0].pixels, job
    breath=next(c for c in audit.show.cues if c.id=="FX_breath_A")
    fast_breath=replace(breath,effect=EffectSpec(mode="fixed",id="breath",speed=1,intensity=1,params={**breath.effect.params,"period":1.2}))
    slow_pixels,_=render(breath,.9); fast_pixels,_=render(fast_breath,.9)
    assert slow_pixels!=fast_pixels, "breath independent period control did not change emitted envelope"
    wave=next(c for c in audit.show.cues if c.id=="FX_color_wave_A")
    fast_wave=replace(wave,effect=EffectSpec(mode="fixed",id="color_wave",speed=9.5,intensity=1,params=wave.effect.params))
    slow_pixels,slow_job=render(wave,1); fast_pixels,fast_job=render(fast_wave,1)
    assert slow_pixels!=fast_pixels and fast_job.effect._phase>slow_job.effect._phase, "color_wave speed control did not change phase/output"
    twinkle=next(c for c in audit.show.cues if c.id=="FX_twinkle_A")
    dense=replace(twinkle,effect=EffectSpec(mode="fixed",id="twinkle",speed=1,intensity=1,params={**twinkle.effect.params,"density":.8}))
    state=random.getstate(); random.seed(SEED)
    try: sparse_pixels,_=render(twinkle,2); random.seed(SEED); dense_pixels,_=render(dense,2)
    finally: random.setstate(state)
    sparse_active=sum(max(pixel)>.01 for pixel in sparse_pixels); dense_active=sum(max(pixel)>.01 for pixel in dense_pixels)
    assert dense_active>sparse_active, f"twinkle density control did not increase independent birth field ({sparse_active} -> {dense_active})"

def test_independent_four_level_controls_measure_effect_specific_progress(audit):
    """Fresh same-id/seed controls retain morphology and measure renderer state/output."""
    resolver=TargetResolver((),(ZoneDef(id=TARGET,pixel_count=20),)); speeds=(2.5,5.,7.5,9.5)
    def run(cue, speed):
        controlled=replace(cue,effect=EffectSpec(mode="fixed",id=cue.effect.id,speed=speed,intensity=1,params=cue.effect.params))
        job=CueRenderJob(controlled,0,resolver,cue_seed=SEED); out=None
        for i in range(31): out=job.render(EffectContext(timestamp=controlled.start+i/FPS,delta_time=1/FPS,sequence=i))
        return job, out.digital[0].pixels
    for family in ("chase","comet","history_stream","heat_fire"):
        cue=next(c for c in audit.show.cues if c.id==f"FX_{family}_A"); jobs=[run(cue,s)[0] for s in speeds]
        if family=="chase": values=[j.effect._position for j in jobs]
        elif family=="comet": values=[j.effect._positions[TARGET] for j in jobs]
        elif family=="history_stream": values=[j.effect._last_steps[TARGET] for j in jobs]
        else: values=[j.effect._last_target_tick for j in jobs]
        assert values==sorted(values) and len(set(values))==4, f"{family}: measured four-level renderer progress {values}"
        if family in {"chase","comet"}:
            for speed in speeds:
                controlled=replace(cue,effect=EffectSpec(mode="fixed",id=cue.effect.id,speed=speed,intensity=1,params=cue.effect.params)); job=CueRenderJob(controlled,0,resolver,cue_seed=SEED)
                first=last=None
                for index in range(31):
                    job.render(EffectContext(timestamp=controlled.start+index/FPS,delta_time=1/FPS,sequence=index))
                    position=job.effect._position if family=="chase" else job.effect._positions[TARGET]
                    if index==0: first=position
                    if index==30: last=position
                local=cue.effect.params["speed"]
                assert (last-first)==pytest.approx(local*speed,abs=1e-7), f"{cue.id}: position delta {last-first}, expected {local*speed}"
    for family in ("single_dot","color_wipe","flowing_bands"):
        cue=next(c for c in audit.show.cues if c.id==f"FX_{family}_A"); pixels=[run(cue,s)[1] for s in speeds]
        signatures=[tuple(round(channel,5) for p in row for channel in p) for row in pixels]
        assert len(set(signatures))==4, f"{family}: four common speeds did not produce four independent measured outputs"

def test_noise_heat_and_color_wave_four_speed_controls_have_numeric_renderer_rates(audit):
    """Measure these three effects at their real renderer integration points."""
    resolver=TargetResolver((),(ZoneDef(id=TARGET,pixel_count=20),)); speeds=(2.5,5.,7.5,9.5)
    def make(cue, speed):
        cue=replace(cue,effect=EffectSpec(mode="fixed",id=cue.effect.id,speed=speed,intensity=1,params=cue.effect.params))
        return cue, CueRenderJob(cue,0,resolver,cue_seed=SEED)
    def drive(cue, job):
        first=last=None
        for index in range(31):
            result=job.render(EffectContext(timestamp=cue.start+index/FPS,delta_time=1/FPS,sequence=index))
            if index==0: first=result
            last=result
        return first,last

    noise=next(c for c in audit.show.cues if c.id=="FX_coherent_noise_field_A")
    import light_engine.effects.coherent_noise_field as noise_module
    original=noise_module.coherent_noise_2d
    try:
        for speed in speeds:
            observed=[]
            def spy(x, temporal, *, seed):
                observed.append(temporal)
                return original(x, temporal, seed=seed)
            noise_module.coherent_noise_2d=spy
            cue,job=make(noise,speed); per_frame=[]
            for index in range(31):
                job.render(EffectContext(timestamp=cue.start+index/FPS,delta_time=1/FPS,sequence=index))
                per_frame.append(observed[-1])  # final .5 zone sample shares the frame temporal coordinate
            delta=per_frame[-1]-per_frame[0]
            assert delta==pytest.approx(.12*speed,abs=1e-9), f"FX_coherent_noise_field_A: temporal coordinate delta {delta}, expected {.12*speed}"
    finally:
        noise_module.coherent_noise_2d=original

    heat=next(c for c in audit.show.cues if c.id=="FX_heat_fire_A")
    transform=_transform(audit.config)
    for speed in speeds:
        cue,job=make(heat,speed); first,last=drive(cue,job)
        before=job.effect._last_target_tick  # state after drive, recorded below through fresh mirror
        # Fresh one-frame control gives exact initial tick; the full drive's tick
        # is the real fixed-step simulation time consumed by HeatFireEffect.
        _,one=make(heat,speed); one.render(EffectContext(timestamp=heat.start,delta_time=1/FPS,sequence=0)); initial=one.effect._last_target_tick
        assert before-initial==pytest.approx(60*speed,abs=1), f"FX_heat_fire_A: ticks {before-initial}, expected {60*speed}"
        assert job.effect._strip_ticks[TARGET]==job.effect._last_target_tick
        first_u8=DigitalStrip(TARGET,20,transform.apply_to_pixels(first.digital[0].pixels)).to_uint8()
        last_u8=DigitalStrip(TARGET,20,transform.apply_to_pixels(last.digital[0].pixels)).to_uint8()
        assert first_u8!=last_u8, _fail("FX_heat_fire_A",cue.start+1,0,last_u8[0],"quantized spatial/time change after fixed ticks")

    wave=next(c for c in audit.show.cues if c.id=="FX_color_wave_A")
    for speed in speeds:
        cue,job=make(wave,speed); first,last=drive(cue,job)
        # The phase is incremented once per process call; difference from first
        # to last spans exactly one wall second (30 intervals).
        phase_last=job.effect._phase
        _,start_job=make(wave,speed); start_job.render(EffectContext(timestamp=wave.start,delta_time=1/FPS,sequence=0))
        assert phase_last-start_job.effect._phase==pytest.approx(.08*speed,abs=1e-9), f"FX_color_wave_A: phase delta {phase_last-start_job.effect._phase}, expected {.08*speed}"

    # Independent implementation of the four native waveform formulas, checked
    # after the production brightness/gamma quantization path.
    for variant in "ABCD":
        cue=next(c for c in audit.show.cues if c.id==f"FX_color_wave_{variant}")
        ctx,frame,state=audit.trace[cue.id][90]
        phase=state["_phase"]; params=cue.effect.params; waveform=params["waveform"]; width=params["width"]; span=params["hue_span_degrees"]
        for group in (0, 7, 15):
            position=(group/20)/width+phase; cycle=position%1
            value=(math.sin(2*math.pi*position)+1)/2 if waveform=="sine" else (1-abs(2*cycle-1) if waveform=="triangle" else (position if waveform=="linear" else cycle))
            hue=(phase*params["hue_cycle_rate"]*360+value*span)%360
            expected=colorsys.hsv_to_rgb(hue/360,1,1)
            expected_u8=DigitalStrip(TARGET,1,transform.apply_to_pixels([expected])).to_uint8()[0]
            actual_u8=DigitalStrip(TARGET,1,transform.apply_to_pixels([frame.strips[0].pixels[group]])).to_uint8()[0]
            assert actual_u8==expected_u8, _fail(cue.id,ctx.timestamp,group,actual_u8,f"independent {waveform} HSV oracle {expected_u8}")

def test_independent_dot_wipe_and_band_controls_match_numeric_progress(audit):
    resolver=TargetResolver((),(ZoneDef(id=TARGET,pixel_count=20),)); speeds=(2.5,5.,7.5,9.5)
    def job(cue,s):
        control=replace(cue,effect=EffectSpec(mode="fixed",id=cue.effect.id,speed=s,intensity=1,params=cue.effect.params))
        return CueRenderJob(control,0,resolver,cue_seed=SEED),control
    dot=next(c for c in audit.show.cues if c.id=="FX_single_dot_A")
    observed=[]
    for speed in speeds:
        item,c=job(dot,speed); output=None
        for i in range(31): output=item.render(EffectContext(timestamp=c.start+i/FPS,delta_time=1/FPS,sequence=i))
        observed.append(next(i for i,p in enumerate(output.digital[0].pixels) if max(p)>0))
    expected=[int((1.0*1.6*speed)//1)%20 for speed in speeds]
    assert observed==expected, f"single_dot: measured group positions {observed}, expected {expected}"
    wipe=next(c for c in audit.show.cues if c.id=="FX_color_wipe_A")
    full_times=[]
    for speed in speeds:
        item,c=job(wipe,speed); first=None
        for i in range(301):
            out=item.render(EffectContext(timestamp=c.start+i/FPS,delta_time=1/FPS,sequence=i))
            if first is None and all(max(p)>0 for p in out.digital[0].pixels): first=i/FPS
        full_times.append(first)
    expected_times=[19/(1.4*speed) for speed in speeds]
    assert all(t is not None and abs(t-want)<=1/FPS for t,want in zip(full_times,expected_times)), f"color_wipe: first full times {full_times}, expected {expected_times}"
    bands=next(c for c in audit.show.cues if c.id=="FX_flowing_bands_A")
    changes=[]
    for speed in speeds:
        item,c=job(bands,speed); highlighted=[]
        for i in range(61):
            out=item.render(EffectContext(timestamp=c.start+i/FPS,delta_time=1/FPS,sequence=i)); values=[max(p) for p in out.digital[0].pixels]
            highlighted.append(next((g for g in range(0,20,2) if values[g]>values[0]+1e-6),-1))
        changes.append(sum(a!=b for a,b in zip(highlighted,highlighted[1:])))
    expected=[math.floor(.8*speed*2) for speed in speeds]
    assert all(abs(actual-want)<=1 for actual,want in zip(changes,expected)), f"flowing_bands: measured changes {changes}, expected steps {expected}"

def test_breath_period_controls_measure_raw_cycles_and_authored_quantized_envelopes(audit):
    resolver=TargetResolver((),(ZoneDef(id=TARGET,pixel_count=20),)); anchor=next(c for c in audit.show.cues if c.id=="FX_breath_A")
    for period in (8.,4.,2.,1.2):
        controlled=replace(anchor,end=anchor.start+18,effect=EffectSpec(mode="fixed",id="breath",speed=1,intensity=1,params={**anchor.effect.params,"period":period}))
        job=CueRenderJob(controlled,0,resolver,cue_seed=SEED); values=[]
        for i in range(int(18*FPS)):
            out=job.render(EffectContext(timestamp=controlled.start+i/FPS,delta_time=1/FPS,sequence=i)); values.append(max(max(p) for p in out.digital[0].pixels))
        peaks=[i for i in range(1,len(values)-1) if values[i]>=values[i-1] and values[i]>values[i+1]-.000001]
        gaps=[(b-a)/FPS for a,b in zip(peaks,peaks[1:]) if (b-a)/FPS>.5]
        assert any(abs(gap-period)<=1/FPS for gap in gaps), f"breath period {period}: measured peak gaps {gaps}"
    for variant,period in zip("ABCD",(8.,4.,2.,1.2)):
        samples=audit.frames[f"FX_breath_{variant}"]; values=[max(max(p) for p in pixels) for _,pixels in samples[3:-3]]
        assert max(values)-min(values)>20, f"FX_breath_{variant}: quantized peak/trough envelope absent (period {period})"

def test_twinkle_density_birth_rate_and_formal_c_birth_memory(audit):
    resolver=TargetResolver((),(ZoneDef(id=TARGET,pixel_count=20),)); anchor=next(c for c in audit.show.cues if c.id=="FX_twinkle_A")
    import light_engine.effects.twinkle as twinkle_module
    original=twinkle_module.random.randrange
    try:
        for density in (.1,.25,.5,.8):
            births=[]
            def count(n): births.append(n); return original(n)
            twinkle_module.random.randrange=count
            cue=replace(anchor,end=anchor.start+4,effect=EffectSpec(mode="fixed",id="twinkle",speed=1,intensity=1,params={**anchor.effect.params,"density":density}))
            state=random.getstate(); random.seed(SEED)
            try:
                job=CueRenderJob(cue,0,resolver,cue_seed=SEED)
                for i in range(120): job.render(EffectContext(timestamp=cue.start+i/FPS,delta_time=1/FPS,sequence=i))
            finally: random.setstate(state)
            assert len(births)==pytest.approx(density*20*4,abs=1), f"twinkle density {density}: births {len(births)}"
    finally: twinkle_module.random.randrange=original
    # C uses the private EVENT sampler.  New growth is measured after expected
    # exponential decay; a width-one, blur-zero event must remain localized.
    entries=audit.trace["FX_twinkle_C"]; proved=0
    def c5(time):
        points=((0.,(.02,.08,.6)),(3.5,(.75,.05,.6)),(7.,(.95,.55,.05)))
        for (a,ca),(b,cb) in zip(points,points[1:]):
            if time<=b:
                q=(time-a)/(b-a); return tuple(x+(y-x)*q for x,y in zip(ca,cb))
        return points[-1][1]
    for entry_index,((ctx,frame,_),(next_ctx,next_frame,_)) in enumerate(zip(entries,entries[1:])):
        previous=frame.strips[0].pixels; current=next_frame.strips[0].pixels; dt=next_ctx.timestamp-ctx.timestamp
        expected=[tuple(channel*math.exp(-dt/.5) for channel in pixel) for pixel in previous]
        born=[i for i,(actual,old) in enumerate(zip(current,expected)) if max(actual)>max(old)+.02]
        if not born: continue
        assert len(born)<=2, _fail("FX_twinkle_C",next_ctx.timestamp,born[0],current[born[0]],"localized event core")
        empty=[group for group in born if max(previous[group])==0]
        if not empty:
            continue  # later events may legitimately overwrite an occupied group
        index=empty[0]
        birth=c5(next_ctx.timestamp-next(c for c in audit.show.cues if c.id=="FX_twinkle_C").start)
        # ColorSampler applies post-effect; inspect its captured contribution.
        contribution=next(c for c in audit.contributions[next_ctx.timestamp] if c.cue_id=="FX_twinkle_C")
        actual_birth=contribution.digital[0].pixels[index]
        assert actual_birth==pytest.approx(birth,abs=1e-7), _fail("FX_twinkle_C",next_ctx.timestamp,index,_u8(transform:=_transform(audit.config).apply_to_frame(compose_frame(audit.bases[next_ctx.timestamp],audit.contributions[next_ctx.timestamp])))[index],f"C5 birth RGB {birth}")
        retained=0
        for later_ctx,later_frame,_ in entries[entry_index+2:]:
            age=later_ctx.timestamp-next_ctx.timestamp; pixel=later_frame.strips[0].pixels[index]
            want=tuple(channel*math.exp(-age/.5) for channel in current[index])
            if pixel==pytest.approx(want,abs=1e-7):
                retained+=1
            else: break
        if retained>=6: proved+=1
    assert proved>0, "FX_twinkle_C: no unoverwritten event retained birth colour for .2s"

def test_history_stream_uses_exact_native_timeline_order_and_write_rate(audit):
    def interpolate(keyframes, time):
        if time<=keyframes[0]["time"]: return tuple(keyframes[0]["color"])
        if time>=keyframes[-1]["time"]: return tuple(keyframes[-1]["color"])
        for left,right in zip(keyframes,keyframes[1:]):
            if time<=right["time"]:
                fraction=(time-left["time"])/(right["time"]-left["time"])
                return tuple(a+(b-a)*fraction for a,b in zip(left["color"],right["color"]))
        raise AssertionError("unreachable timeline")
    for variant,speed,direction in zip("ABCD",(2.5,5.,7.5,9.5),("forward","reverse","forward","reverse")):
        cue=next(c for c in audit.show.cues if c.id==f"FX_history_stream_{variant}")
        rate=.8*speed; keyframes=cue.effect.params["color_timeline"]["keyframes"]
        assert cue.color_source is None and keyframes != next(c for c in audit.show.cues if c.id=="FX_breath_C").color_source.keyframes
        for ctx,frame,state in audit.trace[cue.id][::45]:
            step=math.floor((ctx.timestamp-cue.start)*rate+1e-12)
            assert state["_last_steps"][TARGET]==step, f"{cue.id}: actual write step {state['_last_steps'][TARGET]}, expected {step}"
            for group,actual in enumerate(frame.strips[0].pixels):
                sample=step-group if direction=="forward" else step-(19-group)
                expected=(0.,0.,0.) if sample<0 else interpolate(keyframes,sample/rate)
                assert actual==pytest.approx(expected,abs=1e-7), _fail(cue.id,ctx.timestamp,group,actual,f"raw retained sample {sample} {expected}")
            expected_frame=[(0.,0.,0.) if (step-group if direction=="forward" else step-(19-group))<0 else interpolate(keyframes,(step-group if direction=="forward" else step-(19-group))/rate) for group in range(20)]
            weight=next(c.weight for c in audit.contributions[ctx.timestamp] if c.cue_id==cue.id)
            weighted=[tuple(channel*weight for channel in pixel) for pixel in expected_frame]
            expected_u8=DigitalStrip(TARGET,20,_transform(audit.config).apply_to_pixels(weighted)).to_uint8()
            actual_u8=next(px for stamp,px in audit.frames[cue.id] if stamp==ctx.timestamp)
            assert actual_u8==expected_u8, _fail(cue.id,ctx.timestamp,0,actual_u8[0],f"whole quantized history frame {expected_u8[0]}")
        # 19/rate is the first full capacity time; retained samples must then
        # contain several ordered native colours rather than the shared C5.
        full=next((frame for ctx,frame,_ in audit.trace[cue.id] if ctx.timestamp-cue.start>=19/rate),None)
        assert full is not None and len({p for p in full.strips[0].pixels if max(p)>0})>=2, f"{cue.id}: history did not fill with ordered timeline colours"

def test_independent_twinkle_fade_controls_measure_e_fold_decay(audit):
    resolver=TargetResolver((),(ZoneDef(id=TARGET,pixel_count=20),)); anchor=next(c for c in audit.show.cues if c.id=="FX_twinkle_A")
    transform=_transform(audit.config)
    for fade in (1.2,.8,.5,.3):
        cue=replace(anchor,end=anchor.start+2,effect=EffectSpec(mode="fixed",id="twinkle",speed=1,intensity=1,params={**anchor.effect.params,"fade_time":fade}))
        state=random.getstate(); random.seed(SEED)
        try:
            job=CueRenderJob(cue,0,resolver,cue_seed=SEED); rows=[]
            for i in range(61): rows.append(job.render(EffectContext(timestamp=cue.start+i/FPS,delta_time=1/FPS,sequence=i)).digital[0].pixels)
        finally: random.setstate(state)
        proved=False
        for index,(before,after) in enumerate(zip(rows,rows[1:])):
            born=next((group for group,(old,new) in enumerate(zip(before,after)) if max(old)==0 and max(new)>0),None)
            if born is None: continue
            later=index+1+round(.2*FPS)
            if later>=len(rows): continue
            birth=after[born]; actual=rows[later][born]; expected=tuple(channel*math.exp(-.2/fade) for channel in birth)
            if actual==pytest.approx(expected,abs=1e-7):
                actual_u8=DigitalStrip(TARGET,1,transform.apply_to_pixels([actual])).to_uint8()[0]
                expected_u8=DigitalStrip(TARGET,1,transform.apply_to_pixels([expected])).to_uint8()[0]
                assert actual_u8==expected_u8, _fail("FX_twinkle_A",cue.start+later/FPS,born,actual_u8,f"fade {fade} e-fold {expected_u8}")
                proved=True; break
        assert proved, f"FX_twinkle_A fade_time={fade}: no unoverwritten .2s decay interval"

def test_independent_history_four_speed_controls_measure_native_write_steps(audit):
    resolver=TargetResolver((),(ZoneDef(id=TARGET,pixel_count=20),)); anchor=next(c for c in audit.show.cues if c.id=="FX_history_stream_A")
    for speed in (2.5,5.,7.5,9.5):
        cue=replace(anchor,effect=EffectSpec(mode="fixed",id="history_stream",speed=speed,intensity=1,params=anchor.effect.params))
        job=CueRenderJob(cue,0,resolver,cue_seed=SEED); steps=[]; outputs=[]
        for i in range(31):
            out=job.render(EffectContext(timestamp=cue.start+i/FPS,delta_time=1/FPS,sequence=i)); steps.append(job.effect._last_steps[TARGET]); outputs.append(DigitalStrip(TARGET,20,_transform(audit.config).apply_to_pixels(out.digital[0].pixels)).to_uint8())
        rate=.8*speed; first=next(i for i,value in enumerate(steps) if value>=1)/FPS
        first_index=round(first*FPS)
        assert first==pytest.approx(1/rate,abs=1/FPS), _fail("FX_history_stream_A",cue.start+first,0,outputs[first_index][0],f"first write 1/{rate}")
        assert steps[-1]==math.floor(rate+1e-12), _fail("FX_history_stream_A",cue.start+1,0,outputs[-1][0],f"step {math.floor(rate+1e-12)}")

def test_trace_proves_per_variant_dot_comet_and_c5_geometry(audit):
    # Raw effect frames are traced before compositor recolour/fades, once each.
    for v in "ABCD":
        seen=set()
        for ctx,frame,_ in audit.trace[f"FX_single_dot_{v}"]:
            active=[i for i,p in enumerate(frame.strips[0].pixels) if max(p)>0]
            assert len(active)==1, f"FX_single_dot_{v}: raw effect emitted a tail"
            seen.update(active)
        assert seen==set(range(20)), f"FX_single_dot_{v}: did not individually traverse all groups {set(range(20))-seen}"
    # Multiple bounce heads may meet, but the captured brightest locations must later split again.
    comet=audit.trace["FX_comet_C"]; patterns=[]
    for ctx,frame,_ in comet:
        heads={i for i,p in enumerate(frame.strips[0].pixels) if max(p)>=1-1e-9}
        if len(heads)==2: patterns.append((ctx.timestamp,heads))
    far=[(t,h) for t,h in patterns if max(h)-min(h)>=4]
    merged=[ctx.timestamp for ctx,frame,_ in comet if sum(max(p)>=1-1e-9 for p in frame.strips[0].pixels)==1]
    assert far and merged and any(t<merged[0] for t,_ in far) and any(t>merged[0] for t,_ in far), "FX_comet_C: two heads did not converge then re-separate"
    visible_far=[item for item in far if 134.1<=item[0]<=140.9]
    assert visible_far, "FX_comet_C: no far-apart heads outside transition fades"
    for t,heads in (visible_far[0],visible_far[-1]):
        pixels=next(px for stamp,px in audit.frames["FX_comet_C"] if stamp==t)
        assert all(max(pixels[i])>4 for i in heads), _fail("FX_comet_C",t,min(heads),pixels[min(heads)],"both quantized heads visible")
    # C5 is a whole-seven-second timeline split into cue-local keyframes.  Read
    # the post-ColorSource/post-origin contribution, not the raw white effect.
    def c5_color(local):
        keys=((0.,(.02,.08,.6)),(3.5,(.75,.05,.6)),(7.,(.95,.55,.05)))
        for (a,ca),(b,cb) in zip(keys,keys[1:]):
            if local<=b:
                q=(local-a)/(b-a); return tuple(x+(y-x)*q for x,y in zip(ca,cb))
        return keys[-1][1]
    visible=[]
    for index in range(round(162.4*FPS),round(169.4*FPS)):
        t=index/FPS
        for item in audit.contributions[t]:
            if item.cue_id.startswith("FX_color_wipe_C") and item.weight>0:
                pixels=[p for p in item.digital[0].pixels if p is not None and max(p)>0]
                if pixels: visible.append((item.cue_id,t,max(pixels,key=sum)))
    assert visible, "C5: no post-ColorSource visible contributions"
    for cue_id,t,pixel in visible:
        scale=max(pixel); actual=tuple(channel/scale for channel in pixel)
        wanted=c5_color(t-162.4); wanted=tuple(channel/max(wanted) for channel in wanted)
        assert actual==pytest.approx(wanted,abs=1e-6), _fail(cue_id,t,0,next(px for stamp,px in audit.frames[cue_id] if stamp==t)[0],f"whole-block C5 chroma {wanted}")

def test_trace_proves_twinkle_birth_memory_history_order_and_white_noise_envelope(audit):
    traces=audit.trace["FX_twinkle_C"]
    births=[]
    for (ctx,frame,_),(next_ctx,next_frame,_) in zip(traces,traces[1:]):
        before=frame.strips[0].pixels; after=next_frame.strips[0].pixels
        new=[i for i,(a,b) in enumerate(zip(before,after)) if max(b)>max(a)+.08]
        if new: births.append((ctx,next_ctx,new,before,after))
    assert births, "FX_twinkle_C: no traced EVENT births"
    _,ctx,indices,before,after=births[0]
    assert len(indices)<=2, _fail("FX_twinkle_C",ctx.timestamp,indices[0],after[indices[0]],"local width-one event core")
    assert any(max(after[i])>0 and after[i]!=before[i] for i in indices), "FX_twinkle_C: born colour was not retained in event field"
    for v in "ABCD":
        samples=audit.trace[f"FX_history_stream_{v}"][-1][1].strips[0].pixels
        visible=[p for p in samples if max(p)>0]
        assert len(visible)>=2 and visible[0]!=visible[-1], f"FX_history_stream_{v}: no ordered distinct retained samples"
    # Independent same-id white clone proves spatial continuity from brightness, never palette RGB.
    for v in "ABCD":
        cue=next(c for c in audit.show.cues if c.id==f"FX_coherent_noise_field_{v}")
        params=dict(cue.effect.params); params["color"]=(1.,1.,1.)
        white=replace(cue,effect=EffectSpec(mode="fixed",id=cue.effect.id,speed=cue.effect.speed,intensity=1.,params=params),color=ColorSpec(mode="solid",color=(1.,1.,1.)),color_source=None)
        job=CueRenderJob(white,0,TargetResolver((),(ZoneDef(id=TARGET,pixel_count=20),)),cue_seed=SEED); rows=[]
        for i in range(31): rows.append(job.render(EffectContext(timestamp=white.start+i/FPS,delta_time=1/FPS,sequence=i)).digital[0].pixels)
        levels=[[p[0] for p in row] for row in rows]
        assert any(row!=levels[0] for row in levels[1:]) and max(max(row)-min(row) for row in levels)>.02, f"FX_coherent_noise_field_{v}: white envelope has no temporal/spatial structure"
        assert max(abs(a-b) for row in levels for a,b in zip(row,row[1:]))<.5, f"FX_coherent_noise_field_{v}: white envelope is not spatially continuous"

def test_wipe_full_native_envelope_and_all_twinkle_locality(audit):
    for cue in [c for c in audit.show.cues if c.id.startswith("FX_color_wipe_")]:
        raw={ctx.timestamp:frame.strips[0].pixels for ctx,frame,_ in audit.trace[cue.id]}
        peak=max(cue.color.color) if cue.color.color is not None else 1.0
        full=[]
        for t,pixels in raw.items():
            if t>=cue.end-cue.transition.fade_out or min(max(pixel) for pixel in pixels)<peak-1e-9: continue
            actual=next(px for stamp,px in audit.frames[cue.id] if stamp==t)
            if all(max(pixel)>4 for pixel in actual): full.append(t)
        run=best=0; previous=None
        for t in sorted(full):
            run=run+1 if previous is not None and t-previous<=1/FPS+1e-9 else 1; best=max(best,run); previous=t
        assert best>=9, _fail(cue.id,cue.start,0,(),"nine contiguous raw full-envelope and visible uint8 frames")
    for variant in "ABCD":
        cue_id=f"FX_twinkle_{variant}"; entries=audit.trace[cue_id]; fade=next(c for c in audit.show.cues if c.id==cue_id).effect.params["fade_time"]
        near=[]; maximum=0
        for index,((ctx,frame,_),(next_ctx,next_frame,_)) in enumerate(zip(entries,entries[1:])):
            current=frame.strips[0].pixels; following=next_frame.strips[0].pixels
            actual_current=next(px for stamp,px in audit.frames[cue_id] if stamp==ctx.timestamp)
            near.append(sum(max(pixel)>4 for pixel in actual_current)>=18)
            dt=next_ctx.timestamp-ctx.timestamp; expected=[tuple(channel*math.exp(-dt/fade) for channel in p) for p in current]
            growth=[group for group,(actual,old) in enumerate(zip(following,expected)) if max(actual)>max(old)+1e-7]
            assert len(growth)<=2, _fail(cue_id,next_ctx.timestamp,growth[0] if growth else 0,next(px for stamp,px in audit.frames[cue_id] if stamp==next_ctx.timestamp)[growth[0] if growth else 0],"localized twinkle contribution")
        run=best=0
        for value in near: run=run+1 if value else 0; best=max(best,run)
        assert best<15, f"{cue_id}: sustained near-full 18/20 run was {best} frames"

def test_wipe_origins_are_visible_in_raw_geometry(audit):
    # Origin remapping occurs after raw effect processing; inspect the captured
    # FrameContribution rather than the pre-origin trace frame.
    for name, expected, excluded in (("FX_color_wipe_A",{0},{19}), ("FX_color_wipe_B",{19},{0}), ("FX_color_wipe_C",{9,10},{0,19}), ("FX_color_wipe_D",{0,19},{9,10})):
        found=None
        for t, contributions in sorted(audit.contributions.items()):
            for contribution in contributions:
                if contribution.cue_id==name and contribution.weight>=1-1e-9:
                    pixels=contribution.digital[0].pixels; actual=next(px for stamp,px in audit.frames[name] if stamp==t); active={i for i,p in enumerate(actual) if max(p)>4}
                    if active and active!=set(range(20)): found=(t,pixels,active); break
            if found: break
        assert found is not None, f"{name}: no partial post-origin contribution"
        t,pixels,active=found
        assert expected <= active and not (excluded & active), _fail(name,t,min(expected),next(px for stamp,px in audit.frames[name] if stamp==t)[min(expected)],"expected origin present and opposite region unlit")
