# Vendored web libraries

The Atlas runs offline and its Content-Security-Policy allows `'self'` only, so every
browser library is copied here instead of loaded from a CDN. Only the files the pages
need were kept. Nothing in this folder is edited by hand.

Fetched on 2026-11-01 with `curl` from the npm registry tarballs listed below. Each
tarball's sha512 was checked against the registry's `dist.integrity` before extraction,
and the tarballs were then deleted.

To upgrade: download the new tarball, check its integrity, copy the same files, update
this table (versions and sha256), and test the map, the charts and `/api/docs`.

## Libraries

| Library | Version | Licence | Source tarball | Used by |
|---|---|---|---|---|
| Leaflet | 1.9.4 | BSD-2-Clause (`leaflet/LICENSE`) | `registry.npmjs.org/leaflet/-/leaflet-1.9.4.tgz` | the map page (`index.html`, `js/map.js`) |
| Chart.js | 4.4.7 | MIT (`chartjs/LICENSE.md`) | `registry.npmjs.org/chart.js/-/chart.js-4.4.7.tgz` | every chart, through `common.js` `chart()` |
| swagger-ui-dist | 5.17.14 | Apache-2.0 (`swagger-ui/LICENSE`, `swagger-ui/NOTICE`) | `registry.npmjs.org/swagger-ui-dist/-/swagger-ui-dist-5.17.14.tgz` | `/api/docs` (self-hosted Swagger UI) |

## Files and sha256

Check with `shasum -a 256 -c` after removing the table formatting, or compare by eye.

| File | Copied from (inside the tarball) | sha256 |
|---|---|---|
| `leaflet/leaflet.js` | `package/dist/leaflet.js` | `db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a` |
| `leaflet/leaflet.css` | `package/dist/leaflet.css` | `a7837102824184820dfa198d1ebcd109ff6d0ff9a2672a074b9a1b4d147d04c6` |
| `leaflet/images/layers.png` | `package/dist/images/layers.png` | `1dbbe9d028e292f36fcba8f8b3a28d5e8932754fc2215b9ac69e4cdecf5107c6` |
| `leaflet/images/layers-2x.png` | `package/dist/images/layers-2x.png` | `066daca850d8ffbef007af00b06eac0015728dee279c51f3cb6c716df7c42edf` |
| `leaflet/images/marker-icon.png` | `package/dist/images/marker-icon.png` | `574c3a5cca85f4114085b6841596d62f00d7c892c7b03f28cbfa301deb1dc437` |
| `leaflet/images/marker-icon-2x.png` | `package/dist/images/marker-icon-2x.png` | `00179c4c1ee830d3a108412ae0d294f55776cfeb085c60129a39aa6fc4ae2528` |
| `leaflet/images/marker-shadow.png` | `package/dist/images/marker-shadow.png` | `264f5c640339f042dd729062cfc04c17f8ea0f29882b538e3848ed8f10edb4da` |
| `leaflet/LICENSE` | `package/LICENSE` | `53e8dc25862014e4324741ca18fbe3611e11d42ef69f59f86ea8c5389647d4cb` |
| `chartjs/chart.umd.js` | `package/dist/chart.umd.js` | `2812cb8825fdc57469eb2f7bb055e9429244e599920511ee477e828499b632cb` |
| `chartjs/LICENSE.md` | `package/LICENSE.md` | `41a84aa2caba645f966a18d9c2056b73e6d3a81d80bc0046bc0011a2634d4cce` |
| `swagger-ui/swagger-ui-bundle.js` | `package/swagger-ui-bundle.js` | `c2e4a9ef08144839ff47c14202063ecfe4e59e70a4e7154a26bd50d880c88ba1` |
| `swagger-ui/swagger-ui.css` | `package/swagger-ui.css` | `40170f0ee859d17f92131ba707329a88a070e4f66874d11365e9a77d232f6117` |
| `swagger-ui/LICENSE` | `package/LICENSE` | `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |
| `swagger-ui/NOTICE` | `package/NOTICE` | `0d20d1adef18aee3f40dd258172155521ce702ac445cb5f7b7d60ed32dad2fb2` |

The minified files still end with a `sourceMappingURL` comment. The `.map` files were not
copied, so browser developer tools show a harmless "source map not found" note.
