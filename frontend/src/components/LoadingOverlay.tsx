"use client";

import { useEffect, useState } from "react";

export default function LoadingOverlay() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onStart = () => setVisible(true);
    const onEnd = () => setVisible(false);

    window.addEventListener("flowmind:loading-start", onStart);
    window.addEventListener("flowmind:loading-end", onEnd);

    return () => {
      window.removeEventListener("flowmind:loading-start", onStart);
      window.removeEventListener("flowmind:loading-end", onEnd);
    };
  }, []);

  if (!visible) return null;

  return (
    <div
      className="fixed inset-0 z-[9998] bg-black/30 transition-opacity duration-200"
      aria-hidden="true"
    />
  );
}
