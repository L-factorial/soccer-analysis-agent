import { useEffect, useRef, useState } from "react";
import { Modal, Platform, Pressable, Share, StyleSheet, Text, TextInput, View } from "react-native";
import { getSharedSolution } from "../../api/analyze-field";

export function ShareResultButton({ fieldHash, planId, commentaryLoading }: {
  fieldHash?: string | null;
  planId: string;
  commentaryLoading: boolean;
}) {
  const [visible, setVisible] = useState(false);
  const [url, setUrl] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    setVisible(false);
    return () => request.current?.abort();
  }, [fieldHash, planId]);

  async function prepareLink() {
    if (!fieldHash) return;
    setVisible(true);
    setBusy(true);
    setUrl("");
    setMessage("");
    const controller = new AbortController();
    request.current?.abort();
    request.current = controller;
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const saved = await getSharedSolution(fieldHash, controller.signal);
      const plan = planId === "requested" ? saved.animationResponse
        : saved.animationResponse.alternativePlans?.find((item) => item.id === planId);
      if (!plan) throw new Error("This plan is no longer available. Please select another plan.");
      const base = Platform.OS === "web" ? window.location.href : process.env.EXPO_PUBLIC_WEB_URL;
      if (!base) throw new Error("Sharing needs the website address configured for this app.");
      const link = new URL(base);
      link.search = "";
      link.hash = "";
      link.searchParams.set("fieldHash", fieldHash);
      link.searchParams.set("planId", planId);
      if (plan.commentary) link.searchParams.set("narration", "1");
      if (request.current !== controller) return;
      setUrl(link.toString());
      setMessage(plan.commentary
        ? "Includes saved commentary. Press Play after opening the link to hear it."
        : "Shares the animation. Enable commentary and wait for it to finish before sharing with narration.");
    } catch (error) {
      if (request.current === controller) setMessage(controller.signal.aborted
        ? "Could not load the saved result. Please try again."
        : error instanceof Error ? error.message : "Unable to prepare the share link.");
    } finally {
      clearTimeout(timeout);
      if (request.current === controller) setBusy(false);
    }
  }

  async function copyOrShare() {
    try {
      if (Platform.OS === "web") {
        await navigator.clipboard.writeText(url);
        setMessage("Link copied.");
      } else {
        await Share.share({ message: url, url });
      }
    } catch {
      setMessage("Select and copy the link below to share it.");
    }
  }

  return <>
    <Pressable accessibilityRole="button" disabled={!fieldHash || commentaryLoading || busy}
      style={[styles.button, (!fieldHash || commentaryLoading || busy) && { opacity: 0.45 }]}
      onPress={prepareLink}>
      <Text style={styles.buttonText}>{commentaryLoading ? "Preparing commentary…" : "Share result"}</Text>
    </Pressable>
    <Modal visible={visible} transparent animationType="fade" onRequestClose={() => setVisible(false)}>
      <View style={styles.overlay}>
        <View style={styles.card}>
          <Text style={styles.title}>Share analysis</Text>
          <Text>{busy ? "Preparing your link…" : message}</Text>
          {!!url && <>
            <TextInput accessibilityLabel="Analysis share link" value={url} editable={false}
              selectTextOnFocus style={styles.link} />
            <Text style={styles.note}>Anyone with this link can view the saved field, player names and result. Links expire when removed from the server’s 50-result cache.</Text>
            <Pressable accessibilityRole="button" onPress={copyOrShare} style={styles.button}>
              <Text style={styles.buttonText}>{Platform.OS === "web" ? "Copy link" : "Share link"}</Text>
            </Pressable>
          </>}
          <Pressable accessibilityRole="button" onPress={() => setVisible(false)} style={styles.button}>
            <Text style={styles.buttonText}>Close</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  </>;
}

const styles = StyleSheet.create({
  button: { borderWidth: 1, borderColor: "#B8C8B2", borderRadius: 8, paddingHorizontal: 10, paddingVertical: 7, backgroundColor: "#EEF6E8" },
  buttonText: { color: "#183E2B", fontSize: 12, fontWeight: "700", textAlign: "center" },
  overlay: { flex: 1, justifyContent: "center", alignItems: "center", padding: 20, backgroundColor: "rgba(8,28,19,0.6)" },
  card: { width: "100%", maxWidth: 440, padding: 20, borderRadius: 16, gap: 14, backgroundColor: "#FFFFFF" },
  title: { fontSize: 19, fontWeight: "800", color: "#183E2B" },
  link: { borderWidth: 1, borderColor: "#B8C8B2", borderRadius: 6, padding: 10, color: "#183E2B", fontSize: 12 },
  note: { fontSize: 12, color: "#657264", lineHeight: 18 },
});
