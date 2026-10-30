"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useApiToken } from "@/stores/authStore";
import { resolveWsBaseUrl } from "@/lib/runtime-urls";
import { useQueryClient } from "@tanstack/react-query";
import type { Alert } from "@/lib/api";

export interface WSMessage {
  type: string;
  data?: Record<string, unknown>;
  timestamp?: string;
}

type MessageHandler = (msg: WSMessage) => void;

interface WebSocketContextValue {
  connected: boolean;
  lastMessage: WSMessage | null;
  subscribe: (handler: MessageHandler) => () => void;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const accessToken = useApiToken();
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const handlersRef = useRef<Set<MessageHandler>>(new Set());
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const subscribe = useCallback((handler: MessageHandler) => {
    handlersRef.current.add(handler);
    return () => handlersRef.current.delete(handler);
  }, []);

  const connect = useCallback(function connectWebSocket() {
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
      handlersRef.current.forEach((fn) => fn(msg));
      if (msg.type === "alert" && msg.data) {
        const candidate = msg.data as Partial<Alert>;
        if (
          candidate.id && candidate.title && candidate.message &&
          candidate.severity && candidate.status && candidate.created_at
        ) {
          void queryClient.cancelQueries({ queryKey: ["alerts"] }).then(() => {
            queryClient.setQueryData<Alert[]>(["alerts"], (previous = []) => [
              candidate as Alert,
              ...previous.filter((alert) => alert.id !== candidate.id),
            ].slice(0, 100));
          });
        } else {
          void queryClient.invalidateQueries({ queryKey: ["alerts"] });
        }
      }
      if (msg.type === "attack_detected") {
        void queryClient.invalidateQueries({ queryKey: ["attacks"] });
      }
    };

    ws.onclose = () => {
      if (wsRef.current !== ws) return;
      wsRef.current = null;
      setConnected(false);
      reconnectTimeout.current = setTimeout(connectWebSocket, 5000);
    };

    ws.onerror = () => ws.close();
  }, [accessToken, queryClient]);

  useEffect(() => {
    connect();
    const interval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);

    return () => {
      clearInterval(interval);
      if (reconnectTimeout.current !== null) {
        clearTimeout(reconnectTimeout.current);
        reconnectTimeout.current = null;
      }
      const socket = wsRef.current;
      wsRef.current = null;
      socket?.close();
    };
  }, [connect]);

  return (
    <WebSocketContext.Provider value={{ connected, lastMessage, subscribe }}>
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocketContext() {
  const ctx = useContext(WebSocketContext);
  if (!ctx) {
    throw new Error("useWebSocketContext must be used within WebSocketProvider");
  }
  return ctx;
}

export function useWebSocket(onMessage?: MessageHandler) {
  const { connected, lastMessage, subscribe } = useWebSocketContext();

  useEffect(() => {
    if (!onMessage) return;
    return subscribe(onMessage);
  }, [onMessage, subscribe]);

  return { connected, lastMessage };
}
