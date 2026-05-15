"use client";

import { useMemo, useState } from "react";
import { computeDemurrage, fmtNum, fmtUsd } from "@/lib/calc";

export default function Calculator() {
  const [arrival, setArrival] = useState("");
  const [departure, setDeparture] = useState("");
  const [laytime, setLaytime] = useState(24);
  const [rate, setRate] = useState(300);

  const result = useMemo(() => computeDemurrage({
    arrival_date: arrival || null,
    departure_date: departure || null,
    laytime_hours: Number(laytime) || 0,
    demurrage_usd_per_day: Number(rate) || 0,
  }), [arrival, departure, laytime, rate]);

  return (
    <div className="card">
      <div className="row">
        <label>Arrival
          <input type="datetime-local" value={arrival} onChange={(e) => setArrival(e.target.value)} />
        </label>
        <label>Departure
          <input type="datetime-local" value={departure} onChange={(e) => setDeparture(e.target.value)} />
        </label>
        <label>Laytime (hours)
          <input type="number" step="0.5" value={laytime} onChange={(e) => setLaytime(Number(e.target.value))} />
        </label>
        <label>Rate (USD/day)
          <input type="number" step="1" value={rate} onChange={(e) => setRate(Number(e.target.value))} />
        </label>
      </div>

      <div className="grid grid-4" style={{ marginTop: 14 }}>
        <div className="card kpi"><div className="label">Hours at site</div>
          <div className="value">{fmtNum(result.hoursAtSite, 2)} h</div></div>
        <div className="card kpi"><div className="label">Excess hours</div>
          <div className="value">{fmtNum(result.demurrageHours, 2)} h</div></div>
        <div className="card kpi"><div className="label">Days (no pro-rata)</div>
          <div className="value">{result.demurrageDays}</div></div>
        <div className="card kpi"><div className="label">Amount</div>
          <div className="value" style={{ color: result.amountUsd > 0 ? "var(--red)" : undefined }}>
            {fmtUsd(result.amountUsd)}
          </div></div>
      </div>
      <p className="muted" style={{ marginTop: 10, fontSize: 12 }}>
        Rule: charge starts the moment the truck has been at the unloading site longer than the laytime.
        Each started 24-hour block beyond laytime is billed as one full day (no pro-rata).
      </p>
    </div>
  );
}
