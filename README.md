# Oil Trading Ops

Internal app for an oil trading desk selling **gasoil** and **gasoline** on a
**DDU** basis by truck. It does two things:

1. **Calculates demurrage** for trucks that overstay the agreed laytime at the
   unloading site (rule: laytime in hours, then a flat USD/day per truck,
   *no pro-rata* — every started day beyond laytime is a full day).
2. Gives **visibility on client exposure**: outstanding AR with aging,
   in-transit cargo value, accrued (unbilled) demurrage, and credit-limit
   utilisation per client.

## Stack
- Next.js 14 (App Router, server components, server actions)
- SQLite via `better-sqlite3` (file lives in `./data/ops.db`)
- TypeScript

## Run locally

```bash
npm install
npm run dev
# http://localhost:3000
```

The DB is created and seeded with a few demo clients/deliveries on first run.
Delete `data/ops.db` to start fresh.

## Pages

- **/** Dashboard — KPIs, AR aging, client exposure table, overdue invoices, top demurrage events.
- **/deliveries** Truck-by-truck list with filters; create / edit / mark invoiced / delete.
- **/clients** Counterparties with credit limit, default laytime & demurrage rate, payment terms.
- **/demurrage** Demurrage report + interactive quick calculator.

## Demurrage math

```
hours_at_site   = departure - arrival
excess_hours    = max(0, hours_at_site - laytime_hours)
demurrage_days  = ceil(excess_hours / 24)        # no pro-rata
demurrage_usd   = demurrage_days × rate_usd_per_day
```

The dashboard's **Demurrage Accrued (Unbilled)** KPI is the sum of demurrage
on every delivery where `demurrage_billed = 0` (i.e. not yet charged on an invoice).

## Exposure model

For each client:

```
AR              = Σ outstanding on invoiced deliveries (invoice_total − paid_amount)
In-Transit      = Σ cargo_value of deliveries in 'in_transit' or 'delivered' status
Demurrage       = Σ accrued (unbilled) demurrage
Total exposure  = AR + In-Transit
Utilisation     = Total exposure / credit_limit
```

The dashboard flags clients at ≥80% (HIGH) and ≥100% (OVER LIMIT).

## Notes

- Volumes are in **m³**, prices in **USD/m³**.
- All money is in USD (single-currency model — extend `lib/calc.ts` if you need FX).
- The DB file is git-ignored (`data/`).
