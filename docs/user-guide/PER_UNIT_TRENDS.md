# Per-unit trends from day one: lot quantities

MDARIX's trend check asks the question an inspector asks: is this product version's complaint rate higher than it
should be? Give it how many devices each lot released, and it answers per unit in the field instead of per calendar
day. A version shipped in growing numbers then no longer looks like a rising trend for that reason alone.

## What to export

From your ERP or manufacturing system, one row per lot:

| Column | Required | What it is | Example |
| --- | --- | --- | --- |
| `lot_id` | yes | The lot or batch number | `L24-0815` |
| `product_id` | yes | The product, as in your products file | `PUMP-200` |
| `version` | yes | The product version the lot builds | `Rev D` |
| `manufacture_date` | for per-unit trends | The day the lot was released to the field (YYYY-MM-DD) | `2026-07-20` |
| `quantity` | for per-unit trends | How many devices the lot released, a whole number (`1,250` is fine) | `250` |
| `site_id` | no | The manufacturing site, as in your sites file | `SITE-01` |

Download the lots template from **Import data** (or **Getting started** in a free trial). Its example rows show the
format. Load products first, then lots, then complaints.

## How MDARIX uses it

- Each lot counts from its release day for its quantity: two lots of 250 released on 1 and 15 July give 250 units in the
  field from 1 July and 500 from 15 July.
- When **every** lot of the versions compared has a quantity, the trend check compares complaints per unit-day: the
  last 30 days against the version's own history, or, for a version younger than 90 days, against the version it
  replaced over the 180 days before its release.
- When a lot of a version has no quantity, that version is counted per calendar day, and Signals › Trend check says
  so, with how many groups are affected. The **Counted** column shows which basis each row uses.
- **Single-use products** (0.10.64): the products file's `single_use` column (Y or N) says whether a product's units
  are used up; without it, the `device_category` (single-use, kit and IVD count as used up), and without either, the
  product's words ("disposable", "catheter", "reagent"...). A single-use product is counted per calendar day, or, with
  a `use_period_days` column, by the units still within that many days of their lot's release.

## Updating lots you already loaded

Upload the lots file again with the `quantity` and `manufacture_date` columns filled. Existing lots are updated, not
duplicated; an empty `quantity` cell leaves that lot's quantity as it was.

## Good to know

- Units released is an approximation of devices in use: devices taken out of service still count. Over the 6-month
  window the trend check reads, this is usually small; for devices with a short service life, consider releasing
  quantities net of returns.
- The trend check is a check beside the count rule, never a verdict: a person decides whether a rise is a signal.
- Quantities are business data, not personal data; the import still checks every file for personal data before
  anything is saved.
