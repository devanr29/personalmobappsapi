import type { Icon } from "phosphor-react-native";
import type { ReactNode } from "react";
import { ScrollView } from "react-native";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { useStyles } from "@/theme/useStyles";

export type ListScreenProps<T> = {
  loading: boolean;
  error: string | null;
  data: T | null;
  refetch: () => void;
  skeleton: ReactNode;
  isEmpty?: (data: T) => boolean;
  emptyMessage?: string;
  emptyIcon?: Icon;
  children: (data: T) => ReactNode;
};

export function ListScreen<T>({
  loading,
  error,
  data,
  refetch,
  skeleton,
  isEmpty,
  emptyMessage,
  emptyIcon,
  children,
}: ListScreenProps<T>) {
  const styles = useStyles((t) => ({
    scroll: { flex: 1, backgroundColor: t.colors.bg },
    content: { padding: t.spacing[4], paddingTop: t.spacing[5], paddingBottom: t.spacing[3] },
  }));

  if (loading) {
    return (
      <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
        {skeleton}
      </ScrollView>
    );
  }

  if (error || data === null) {
    return <ErrorState message={error ?? "Couldn't load data."} onRetry={refetch} />;
  }

  if (isEmpty && emptyMessage && isEmpty(data)) {
    return <EmptyState message={emptyMessage} IconComponent={emptyIcon} />;
  }

  return <>{children(data)}</>;
}
