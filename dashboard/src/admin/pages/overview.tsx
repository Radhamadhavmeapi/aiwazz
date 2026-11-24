import { PageHeader } from "../components/page";
import { AdminShell } from "../components/shell";

export default function OverviewPage() {
  return (
    <AdminShell title="Overview">
      <PageHeader title="Overview" description="KPIs, charts and the latest activity." />
    </AdminShell>
  );
}
