import { useState, useCallback, useEffect, useRef } from 'react';
import { Alert } from '../lib/api';

export interface CriticalAlert extends Alert {
  isNew: boolean;
  notificationSent: boolean;
}

interface UseCriticalAlertsConfig {
  enabled?: boolean;
  soundEnabled?: boolean;
  notificationsEnabled?: boolean;
}

export function useCriticalAlerts(
  alerts: Alert[],
  config: UseCriticalAlertsConfig = {}
) {
  const {
    enabled = true,
    soundEnabled = true,
    notificationsEnabled = true,
  } = config;

  const [criticalAlerts, setCriticalAlerts] = useState<CriticalAlert[]>([]);
  const [hasNewCritical, setHasNewCritical] = useState(false);
  const audioContextRef = useRef<AudioContext | null>(null);
  const notificationRef = useRef<Notification | null>(null);

  // Get critical alerts (high or medium with acknowledged status)
  const getCriticalAlerts = useCallback(() => {
    if (!enabled) return [];

    return alerts.filter(
      (alert) =>
        (alert.riskLevel === 'high' ||
          (alert.riskLevel === 'medium' && alert.status === 'acknowledged')) &&
        alert.status !== 'completed'
    );
  }, [alerts, enabled]);

  // Play alert sound
  const playAlertSound = useCallback(async () => {
    if (!soundEnabled) return;

    try {
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
      }

      const ctx = audioContextRef.current;
      const now = ctx.currentTime;
      const duration = 0.5;

      // Create two beeps with different frequencies
      const frequencies = [800, 1200]; // Hz

      for (let i = 0; i < 2; i++) {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.frequency.value = frequencies[i % 2];
        gain.gain.setValueAtTime(0.3, now + i * duration);
        gain.gain.exponentialRampToValueAtTime(0.01, now + (i + 1) * duration);

        osc.start(now + i * duration);
        osc.stop(now + (i + 1) * duration);
      }
    } catch (error) {
      console.error('Failed to play alert sound:', error);
    }
  }, [soundEnabled]);

  // Send desktop notification
  const sendNotification = useCallback(async (alert: Alert) => {
    if (!notificationsEnabled || !('Notification' in window)) return;

    // Request permission if needed
    if (Notification.permission === 'default') {
      await Notification.requestPermission();
    }

    if (Notification.permission === 'granted') {
      try {
        // Close previous notification
        if (notificationRef.current) {
          notificationRef.current.close();
        }

        // Calculate time in immobility
        const imobilizadoMin = alert.lastRepositioning 
          ? Math.floor((Date.now() - new Date(alert.lastRepositioning).getTime()) / 60000)
          : 0;

        // Build location string
        const location = alert.room && alert.bed 
          ? `${alert.room} / ${alert.bed}`
          : alert.bed || alert.room || 'Sem leito';

        // Map risk level to Portuguese
        const riskMap: Record<string, string> = {
          'high': 'ALTO',
          'medium': 'MÉDIO',
          'low': 'BAIXO'
        };
        const riskPT = riskMap[alert.riskLevel] || alert.riskLevel.toUpperCase();

        // Create new notification
        const title = `🚨 Alerta Crítico - ${alert.patientName}`;
        const options: NotificationOptions = {
          body: `📍 ${location}\n⏱️ Imobilizado há ${imobilizadoMin}min\n⚠️ Perfil: ${riskPT}\n🔄 Próximo reposicionamento: ${new Date(
            alert.nextRepositioning
          ).toLocaleTimeString('pt-BR')}`,
          icon: '/icon-alert.png',
          badge: '/badge-alert.png',
          tag: `critical-alert-${alert.id}`,
          requireInteraction: true,
        };

        notificationRef.current = new Notification(title, options);

        // Handle notification click
        notificationRef.current.addEventListener('click', () => {
          window.focus();
          window.scrollTo(0, 0);
        });
      } catch (error) {
        console.error('Failed to send notification:', error);
      }
    }
  }, [notificationsEnabled]);

  // Update critical alerts and trigger notifications
  useEffect(() => {
    if (!enabled) return;

    const newCritical = getCriticalAlerts();
    const previousCritical = criticalAlerts;

    // Detect new critical alerts
    const newAlerts = newCritical.filter(
      (alert) => !previousCritical.some((prev) => prev.id === alert.id)
    );

    if (newAlerts.length > 0) {
      setHasNewCritical(true);

      // Play sound for each new critical alert
      for (const alert of newAlerts) {
        playAlertSound();
        sendNotification(alert);
      }

      // Update critical alerts with isNew flag
      const updated = newCritical.map((alert) => ({
        ...alert,
        isNew: newAlerts.some((a) => a.id === alert.id),
        notificationSent: newAlerts.some((a) => a.id === alert.id),
      }));

      setCriticalAlerts(updated);

      // Reset hasNewCritical after 5 seconds
      setTimeout(() => setHasNewCritical(false), 5000);
    } else {
      setCriticalAlerts(newCritical.map((alert) => ({ ...alert, isNew: false, notificationSent: false })));
    }
  }, [alerts, enabled, getCriticalAlerts, playAlertSound, sendNotification]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (notificationRef.current) {
        notificationRef.current.close();
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, []);

  const highRiskCount = criticalAlerts.filter((a) => a.riskLevel === 'high').length;
  const acknowledgedMediumCount = criticalAlerts.filter(
    (a) => a.riskLevel === 'medium' && a.status === 'acknowledged'
  ).length;

  return {
    criticalAlerts,
    totalCritical: criticalAlerts.length,
    highRisk: highRiskCount,
    acknowledgedMedium: acknowledgedMediumCount,
    hasNewCritical,
    playAlertSound,
    sendNotification,
  };
}
