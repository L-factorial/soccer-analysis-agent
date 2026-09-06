import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { AnalysisMetrics, getAnalysisMetrics } from "../../api/analyze-field";

export function AnalysisMetricsDisplay({ refreshKey }: { refreshKey: string }) {
  const [metrics, setMetrics] = useState<AnalysisMetrics | null>(null);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController;
    async function refresh() {
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 4000);
      try {
        const next = await getAnalysisMetrics(controller.signal);
        if (!stopped) setMetrics(next);
      } catch {
        if (!stopped) setMetrics(null);
      } finally {
        clearTimeout(timeout);
        if (!stopped) timer = setTimeout(refresh, 5000);
      }
    }
    void refresh();
    return () => {
      stopped = true;
      clearTimeout(timer);
      controller?.abort();
    };
  }, [refreshKey]);

  return (
    <View style={styles.container} accessibilityLabel={metrics
      ? `${metrics.ongoingAnalyses} ongoing analyses, ${metrics.analysesLast24Hours} analyses started in the last 24 hours`
      : "Analysis metrics unavailable"}>
      <View style={styles.item}>
        <Text style={styles.value}>{metrics?.ongoingAnalyses ?? "—"}</Text>
        <Text style={styles.label}>Ongoing</Text>
      </View>
      <View style={styles.divider} />
      <View style={styles.item}>
        <Text style={styles.value}>{metrics?.analysesLast24Hours ?? "—"}</Text>
        <Text style={styles.label}>Started · 24h</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row", alignItems: "center", gap: 10,
    borderWidth: 1, borderColor: "#DCE4D9", borderRadius: 8,
    backgroundColor: "#F5F8F2", paddingHorizontal: 10, paddingVertical: 5,
  },
  item: { alignItems: "center", gap: 1 },
  value: { fontSize: 13, fontWeight: "800", color: "#183E2B", fontVariant: ["tabular-nums"] },
  label: { fontSize: 9, color: "#657264" },
  divider: { width: 1, height: 22, backgroundColor: "#DCE4D9" },
});
