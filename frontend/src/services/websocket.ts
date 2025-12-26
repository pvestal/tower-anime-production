/**
 * WebSocket Service for Real-time Updates
 * Handles live progress tracking for generation jobs
 */

export interface ProgressUpdate {
  job_id: string;
  status: string;
  progress: number;
  current_step?: string;
  message?: string;
  error?: string;
  result?: any;
  timestamp: string;
}

export interface WebSocketConfig {
  url?: string;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

export class WebSocketService {
  private ws: WebSocket | null = null;
  private url: string;
  private jobId: string | null = null;
  private reconnectInterval: number;
  private maxReconnectAttempts: number;
  private reconnectAttempts: number = 0;
  private listeners: Map<string, Set<(data: any) => void>> = new Map();
  private reconnectTimer: NodeJS.Timeout | null = null;
  private isConnecting: boolean = false;
  private heartbeatTimer: NodeJS.Timeout | null = null;

  constructor(config: WebSocketConfig = {}) {
    // Build WebSocket URL dynamically based on current protocol and host
    const wsPath = import.meta.env.VITE_WS_URL || '/api/anime/ws';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const baseUrl = `${protocol}//${host}${wsPath}`;

    this.url = config.url || baseUrl;
    this.reconnectInterval = config.reconnectInterval || 3000;
    this.maxReconnectAttempts = config.maxReconnectAttempts || 10;
  }

  /**
   * Connect to WebSocket server for a specific job
   */
  connect(jobId: string): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.isConnecting) {
        reject(new Error('Already connecting'));
        return;
      }

      this.jobId = jobId;
      this.isConnecting = true;

      // Construct WebSocket URL with job ID
      const wsUrl = `${this.url}/ws/job/${jobId}`;

      try {
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
          console.log(`WebSocket connected for job ${jobId}`);
          this.isConnecting = false;
          this.reconnectAttempts = 0;
          this.startHeartbeat();
          this.emit('connected', { job_id: jobId });
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
          }
        };

        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          this.isConnecting = false;
          this.emit('error', { error: 'WebSocket connection error' });
          reject(error);
        };

        this.ws.onclose = () => {
          console.log('WebSocket disconnected');
          this.isConnecting = false;
          this.stopHeartbeat();
          this.emit('disconnected', { job_id: jobId });
          this.attemptReconnect();
        };

      } catch (error) {
        this.isConnecting = false;
        reject(error);
      }
    });
  }

  /**
   * Connect using Server-Sent Events (SSE) as fallback
   */
  connectSSE(jobId: string): EventSource {
    const sseUrl = `${this.url.replace('ws://', 'http://').replace('wss://', 'https://')}/api/anime/orchestration/job/${jobId}/stream`;
    const eventSource = new EventSource(sseUrl);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.handleMessage(data);
      } catch (error) {
        console.error('Failed to parse SSE message:', error);
      }
    };

    eventSource.onerror = () => {
      console.error('SSE connection error');
      this.emit('error', { error: 'SSE connection error' });
      eventSource.close();
    };

    return eventSource;
  }

  /**
   * Handle incoming messages
   */
  private handleMessage(data: any) {
    // Emit based on message type
    if (data.type) {
      this.emit(data.type, data);
    }

    // Emit progress updates
    if (data.progress !== undefined) {
      const update: ProgressUpdate = {
        job_id: data.job_id || this.jobId!,
        status: data.status,
        progress: data.progress,
        current_step: data.current_step || data.message,
        message: data.message,
        error: data.error,
        result: data.result,
        timestamp: data.timestamp || new Date().toISOString()
      };

      this.emit('progress', update);

      // Emit status-specific events
      if (data.status) {
        this.emit(`status:${data.status}`, update);
      }
    }

    // Handle job completion
    if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
      this.emit('complete', data);

      // Auto-disconnect after completion
      setTimeout(() => {
        this.disconnect();
      }, 1000);
    }
  }

  /**
   * Send message to server
   */
  send(data: any): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  /**
   * Subscribe to events
   */
  on(event: string, callback: (data: any) => void): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(callback);
  }

  /**
   * Unsubscribe from events
   */
  off(event: string, callback: (data: any) => void): void {
    if (this.listeners.has(event)) {
      this.listeners.get(event)!.delete(callback);
    }
  }

  /**
   * Emit events to listeners
   */
  private emit(event: string, data: any): void {
    if (this.listeners.has(event)) {
      this.listeners.get(event)!.forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error(`Error in listener for event ${event}:`, error);
        }
      });
    }
  }

  /**
   * Heartbeat to keep connection alive
   */
  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.send({ type: 'ping' });
      }
    }, 30000); // Ping every 30 seconds
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  /**
   * Attempt to reconnect
   */
  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      this.emit('max_reconnect_reached', {});
      return;
    }

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }

    this.reconnectAttempts++;
    console.log(`Attempting reconnection ${this.reconnectAttempts}/${this.maxReconnectAttempts}...`);

    this.reconnectTimer = setTimeout(() => {
      if (this.jobId) {
        this.connect(this.jobId).catch(error => {
          console.error('Reconnection failed:', error);
        });
      }
    }, this.reconnectInterval);
  }

  /**
   * Disconnect WebSocket
   */
  disconnect(): void {
    this.stopHeartbeat();

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.jobId = null;
    this.reconnectAttempts = 0;
    this.listeners.clear();
  }

  /**
   * Get connection state
   */
  get isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  get connectionState(): string {
    if (!this.ws) return 'disconnected';
    switch (this.ws.readyState) {
      case WebSocket.CONNECTING: return 'connecting';
      case WebSocket.OPEN: return 'connected';
      case WebSocket.CLOSING: return 'closing';
      case WebSocket.CLOSED: return 'closed';
      default: return 'unknown';
    }
  }
}

// Singleton instance for app-wide use
let sharedInstance: WebSocketService | null = null;

export function getWebSocketService(config?: WebSocketConfig): WebSocketService {
  if (!sharedInstance) {
    sharedInstance = new WebSocketService(config);
  }
  return sharedInstance;
}

export default WebSocketService;