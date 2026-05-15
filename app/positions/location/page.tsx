import { locationPositions, fmtNum } from "@/lib/calc";

export const dynamic = "force-dynamic";

export default function ByLocation() {
  const positions = locationPositions();

  return (
    <>
      <h1>By Location & Product</h1>
      <p className="muted">Positions derived from deals × loadings. Identical numbers to the per-location books in your workbook, with no risk of stale copies.</p>

      <div className="card" style={{ padding: 0, marginTop: 12 }}>
        {positions.length === 0 ? <div className="empty">No positions to show. Add some deals first.</div> : (
          <table>
            <thead>
              <tr>
                <th>Location</th><th>Product</th>
                <th className="num">Purchased</th>
                <th className="num">Sold</th>
                <th className="num">Unsold</th>
                <th className="num">Loaded (P)</th>
                <th className="num">Loaded (S)</th>
                <th className="num">FCA sold but not loaded</th>
                <th className="num">Physical Bal.</th>
                <th className="num">In Tank Unsold</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={`${p.locationCode}-${p.productCode}`}>
                  <td>{p.locationName} <span className="tag">{p.locationCode}</span></td>
                  <td><span className={`badge ${p.productCode === "AGO" ? "amber" : p.productCode === "PMS" ? "purple" : "blue"}`}>{p.productCode}</span></td>
                  <td className="num">{fmtNum(p.purchasedM3, 0)}</td>
                  <td className="num">{fmtNum(p.soldM3, 0)}</td>
                  <td className="num">{fmtNum(p.unsoldM3, 0)}</td>
                  <td className="num">{fmtNum(p.loadedPurchM3, 0)}</td>
                  <td className="num">{fmtNum(p.loadedSaleM3, 0)}</td>
                  <td className="num">{fmtNum(p.fcaSoldNotNomM3, 0)}</td>
                  <td className="num"><strong>{fmtNum(p.physicalBalanceM3, 0)}</strong></td>
                  <td className="num">{fmtNum(p.inTankUnsoldM3, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
