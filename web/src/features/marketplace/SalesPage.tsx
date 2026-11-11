import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { payments } from "../../api/endpoints";
import { Icon } from "../../components/Icon";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { dateTime } from "../../components/labels";
import { useI18n } from "../../i18n";

function money(cents: number, currency: string): string {
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(cents / 100);
}

/** For authors: setting up payments (where to be paid) and what has been sold. */
export function SalesPage() {
  const { t } = useI18n();
  const payout = useQuery({ queryKey: ["payout"], queryFn: payments.payout });
  const sales = useQuery({ queryKey: ["sales"], queryFn: payments.sales });
  const setup = useMutation({
    mutationFn: payments.onboarding,
    onSuccess: ({ url }) => window.location.assign(url),
  });
  return (
    <div className="page sales-overview">
      <p className="breadcrumbs">
        <Link to="/marketplace">← {t("nav.marketplace")}</Link>
      </p>
      <div className="page-header">
        <h1>{t("sell.title")}</h1>
        <p className="hint">{t("sell.intro")}</p>
      </div>
      <QueryState query={payout}>
        {(status) => (
          <section className="card payout-card" aria-labelledby="payout-title">
            <h2 id="payout-title" className="with-icon">
              <Icon name="receipt" size={20} /> {t("sell.payments")}
            </h2>
            {!status.enabled ? (
              <p>{t("sell.off")}</p>
            ) : status.ready ? (
              <>
                <p className="banner success">{t("sell.ready")}</p>
                <p className="hint">{t("sell.feeNote", { n: status.fee_percent })}</p>
              </>
            ) : (
              <>
                <p>{status.account ? t("sell.pending") : t("sell.start")}</p>
                <ol className="steps">
                  <li>{t("sell.step1")}</li>
                  <li>{t("sell.step2")}</li>
                  <li>{t("sell.step3", { n: status.fee_percent })}</li>
                </ol>
                <button type="button" className="primary" disabled={setup.isPending} onClick={() => setup.mutate()}>
                  {setup.isPending ? t("common.pleaseWait") : status.account ? t("sell.continue") : t("sell.setup")}
                </button>
                <ErrorBanner error={setup.error} />
              </>
            )}
          </section>
        )}
      </QueryState>
      <QueryState query={sales}>
        {(data) => (
          <section className="card" aria-labelledby="sales-title">
            <h2 id="sales-title">{t("sell.sales")}</h2>
            {data.items.length === 0 ? (
              <p className="hint">{t("sell.none")}</p>
            ) : (
              <>
                <dl className="stats">
                  <div className="stat">
                    <dt>{t("sell.count")}</dt>
                    <dd>{data.count}</dd>
                  </div>
                  <div className="stat">
                    <dt>{t("sell.gross")}</dt>
                    <dd>{money(data.gross_cents, data.currency)}</dd>
                  </div>
                  <div className="stat">
                    <dt>{t("sell.net")}</dt>
                    <dd>{money(data.net_cents, data.currency)}</dd>
                  </div>
                </dl>
                <div className="table-scroll">
                  <table className="sales-table">
                    <thead>
                      <tr>
                        <th scope="col">{t("sell.colCourse")}</th>
                        <th scope="col">{t("sell.colDate")}</th>
                        <th scope="col">{t("sell.colPrice")}</th>
                        <th scope="col">{t("sell.colNet")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.items.map((sale) => (
                        <tr key={sale.id} className={sale.refunded ? "refunded" : undefined}>
                          <td>
                            <Link to={`/marketplace/${sale.listing_id}`}>{sale.title}</Link>
                            {sale.refunded && <span className="pill"> {t("sell.refunded")}</span>}
                          </td>
                          <td>{dateTime(sale.paid_at)}</td>
                          <td>{money(sale.amount_cents, sale.currency)}</td>
                          <td>{sale.refunded ? "—" : money(sale.net_cents, sale.currency)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="hint">{t("sell.netNote")}</p>
              </>
            )}
          </section>
        )}
      </QueryState>
    </div>
  );
}
