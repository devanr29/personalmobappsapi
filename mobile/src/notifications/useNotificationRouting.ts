import * as Notifications from "expo-notifications";
import { router } from "expo-router";
import { useEffect } from "react";

// Taps on a push open the matching screen. Only the Quran verse push
// (features/quran.py send_scheduled_verse) carries routing data today:
// { verse: "2:255" } opens Chat, which sends "quran 2:255" once.
function handle(response: Notifications.NotificationResponse | null) {
  const verse = response?.notification.request.content.data?.verse;
  if (typeof verse !== "string" || !verse) return;
  // Clear it so a later cold start doesn't replay the same tap.
  Notifications.clearLastNotificationResponse();
  router.push({ pathname: "/chat", params: { verse } });
}

export function useNotificationRouting() {
  useEffect(() => {
    // Cold start: the tap that launched the app arrives before any listener.
    handle(Notifications.getLastNotificationResponse());
    const subscription = Notifications.addNotificationResponseReceivedListener(handle);
    return () => subscription.remove();
  }, []);
}
