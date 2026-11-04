# Corresponding source and customer notice — preparation record

**NOT READY FOR CUSTOMER DELIVERY.** No seller/contact, final binary inventory, matching source archive, verified download location or approved written offer is established. This document is a preparation record, not a promise that a source service currently exists. Do not print a placeholder link on the product.

The shortest supported route for the first physical release is to put the required notices, exact third-party source and build/relinking material on media accompanying the hardware, rather than relying on an untested written offer. Do not put proprietary application source in that collection merely because it shares the system image. Review each applicable license's precise delivery route.

| Shipped component | Source/relinking record required before sale | License basis |
|---|---|---|
| Stock WLED / vendor WLED | Verify model, all installed firmware versions, build IDs and hashes. Identify matching upstream tag/commit and vendor patches/configuration needed to rebuild. For EUPL versions, include source or an easily/freely accessible source repository with the copyright notice, available throughout distribution. Preserve firmware credits. | Actual version/file licenses govern: modern EUPL Articles 3 and 5 require source; older v0.14.4 has MIT text and must be checked with its bundled components. A generic WLED home page is insufficient for an exact-source obligation. |
| Modified WLED | All source changes forming the covered derivative work, applicable notices/change dates and rebuild configuration; identify a valid applicable copyleft license. | EUPL Article 5; compatibility is conditional, not arbitrary relicensing. |
| GPL mpv / GPL FFmpeg / kernel / other GPL image packages | Exact upstream source plus distro/vendor patches, relevant compilation and installation scripts and other corresponding-source material. Record binary/source package versions, archive hashes and included notice locations. Select and satisfy the actual GPLv2 section 3 or GPLv3 section 6 distribution route. | GPL-2.0 sections 2–3; GPL-3.0 sections 5–6. If GPLv3 User Product provisions apply, include required Installation Information; determine this from the actual components/device. |
| LGPL FFmpeg / libsndfile / other LGPL native libraries | Matching source and changes plus license notices; confirm the delivered linkage form and permitted replacement of the library. Static linking needs the applicable relinkable application object code/material or another valid route; the LGPL does not invariably require proprietary application source. | LGPL-2.1 sections 4 and 6, or LGPL-3.0 section 4 with GPLv3 as applicable. License permissions required for debugging modifications cannot be removed by customer terms. |
| Arduino custom firmware, if included | Pin/record resolved frameworks and every library, retain original notices and provide library source and a workable relinking route for static combinations under their actual terms. Distinguish SDK blobs/toolchain exceptions from framework license. | Exact LGPL version/component terms govern. Reference licenses alone do not clear the unresolved build. |
| GCC runtime subject to Runtime Library Exception 3.1 | Retain applicable notices and verify the target compilation qualifies for the exception. Do not interpret GPL text embedded in SciPy notices without the accompanying exception. | GCC Runtime Library Exception 3.1 sections 1–2. It permits eligible target-code combinations without imposing the runtime library's GPL on independent modules. |
| certifi / MPL-covered certificate bundle, if shipped | Identify covered files and whether the delivered PEM/files already are Source Code Form. Preserve their license notices and MPL access; provide the required notice and means to obtain covered Source Code Form if distributing Executable Form. Confirm target-file provenance and modifications rather than assuming the package is binary-only. | MPL-2.0 sections 3.1–3.4. Section 3.3 permits other terms for the larger independently authored application; it does not require its complete source or a relinking kit. |

## Per-release source record

Before sale, a human release owner must complete and verify all of these fields for each applicable shipped binary:

1. Product/release ID, seller's legal name and service contact, sales territories and distribution channel.
2. Binary filename/package/device build identifier, version, SHA-256 and copy of its original copyright/license notices.
3. Exact matching source archive/commit, downstream patches, build options, dependency versions, compilation/install scripts and source-archive SHA-256.
4. Chosen permitted delivery method, actual included media location or working download URL, customer-visible notice, availability/retention responsibility and any applicable duration.
5. Practical source retrieval and build/relinking/installation check appropriate to that component. A license link or a successful application unit test is not this check.
6. Proprietary-code boundary and approved customer terms, excluding third-party components from any conflicting source, modification or reverse-engineering restrictions.

No source URL, supplier warranty or firmware identity has been invented in this audit. Product release remains blocked until the [open risks](docs/compliance/OPEN_RISKS.md) have evidence-based closure.
