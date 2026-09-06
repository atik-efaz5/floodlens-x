import { useEffect, useState } from "react";
import { formatTime } from "../constants";

export function useTimeAnimation(availableTimes, enabled) {
  const times = Array.isArray(availableTimes) ? availableTimes : [];
  const [index, setIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);

  const timeKey = times.join(",");

  useEffect(() => {
    if (times.length === 0) {
      setIndex(0);
      return;
    }
    setIndex(times.length - 1);
    setIsPlaying(false);
  }, [timeKey]);

  const currentTime = times.length > 0 ? times[Math.min(index, times.length - 1)] : 0;
  const duration = times.length > 0 ? times[times.length - 1] : 0;
  const timeFraction =
    times.length <= 1 ? 1 : Math.min(index, times.length - 1) / (times.length - 1);

  useEffect(() => {
    if (!enabled || !isPlaying || times.length === 0) {
      return undefined;
    }

    const interval = window.setInterval(() => {
      setIndex((previous) => {
        if (previous >= times.length - 1) {
          setIsPlaying(false);
          return times.length - 1;
        }
        return previous + 1;
      });
    }, 400);

    return () => window.clearInterval(interval);
  }, [enabled, isPlaying, times.length]);

  const handlePlayPause = () => {
    if (!enabled || times.length === 0) {
      return;
    }
    if (index >= times.length - 1) {
      setIndex(0);
    }
    setIsPlaying((playing) => !playing);
  };

  const handleReset = () => {
    setIsPlaying(false);
    setIndex(0);
  };

  const handleScrub = (value) => {
    setIsPlaying(false);
    const nextIndex = Number(value);
    if (!Number.isFinite(nextIndex)) {
      return;
    }
    setIndex(Math.max(0, Math.min(times.length - 1, Math.round(nextIndex))));
  };

  return {
    currentTime,
    duration,
    timeFraction,
    timeIndex: index,
    availableTimes: times,
    isPlaying,
    isCollapsed,
    setIsCollapsed,
    handlePlayPause,
    handleReset,
    handleScrub,
    formattedCurrent: formatTime(currentTime),
    formattedDuration: formatTime(duration),
  };
}
