import { useState, useEffect, useCallback } from 'react';
import type { Task } from '../types';

export function useTasks(companyId: string) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTasks = useCallback(async () => {
    try {
      setLoading(true);
      // TODO: Implement actual API call via Tauri IPC
      setTasks([]);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch tasks');
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  return { tasks, loading, error, refetch: fetchTasks };
}

export function useCreateTask(companyId: string) {
  const [creating, setCreating] = useState(false);

  const createTask = useCallback(async (_title: string, _description?: string) => {
    try {
      setCreating(true);
      // TODO: Implement actual API call via Tauri IPC
      return true;
    } catch (e) {
      console.error('Failed to create task:', e);
      return false;
    } finally {
      setCreating(false);
    }
  }, [companyId]);

  return { createTask, creating };
}
