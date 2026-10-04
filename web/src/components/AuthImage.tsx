import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";

/**
 * An image the API only gives with the access token (a drawing), so it can't be a plain
 * <img src>: fetched as a blob and shown through an object URL, released when no longer shown.
 */
export function AuthImage({ queryKey, load, alt, className }: { queryKey: readonly unknown[]; load: () => Promise<Blob>; alt: string; className?: string }) {
  const blob = useQuery({ queryKey, queryFn: load, staleTime: Infinity });
  const url = useMemo(() => (blob.data ? URL.createObjectURL(blob.data) : null), [blob.data]);
  useEffect(() => () => {
    if (url) URL.revokeObjectURL(url);
  }, [url]);
  if (blob.isError) return <p className="hint">The drawing couldn't be loaded.</p>;
  if (!url) return <div className={`${className ?? ""} image-loading`} aria-busy="true" />;
  return <img src={url} alt={alt} className={className} />;
}
