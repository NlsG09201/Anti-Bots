"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useAuthStore } from "@/stores/authStore";
import { resolveWsBaseUrl } from "@/lib/runtime-urls";

export interface WSMessage {
  type: string;
  data?: Record<string, unknown>;
  timestamp?: string;
}

export function useWebSocket(onMessage?: (msg: WSMessage) => void) {
  const { accessToken } = useAuthStore();
  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<NodeJS.Timeout>();

  const connect = useCallback(() => {
    if (!accessToken) return;

    const wsUrl = resolveWsBaseUrl();
    if (!wsUrl) return;

    const ws = new WebSocket(`${wsUrl}/ws/live?token=${accessToken}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      ws.send(JSON.stringify({ type: "subscribe", channel: "all" }));
    };

    ws.onmessage = (event) => {
      const msg: WSMessage = JSON.parse(event.data);
      setLastMessage(msg);
      onMessage?.(msg);
    };

    ws.onclose = () => {
      setConnected(false);
      reconnectTimeout.current = setTimeout(connect, 5000);
    };

    ws.onerror = () => ws.close();
  }, [accessToken, onMessage]);

  useEffect(() => {
    connect();
    const interval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);

    return () => {
      clearInterval(interval);
      clearTimeout(reconnectTimeout.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected, lastMessage };
}
