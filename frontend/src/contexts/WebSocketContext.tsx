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
  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const handlersRef = useRef<Set<MessageHandler>>(new Set());
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout>>();

  const subscribe = useCallback((handler: MessageHandler) => {
    handlersRef.current.add(handler);
    return () => handlersRef.current.delete(handler);
  }, []);

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
      handlersRef.current.forEach((fn) => fn(msg));
    };

    ws.onclose = () => {
      setConnected(false);
      reconnectTimeout.current = setTimeout(connect, 5000);
    };

    ws.onerror = () => ws.close();
  }, [accessToken]);

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
