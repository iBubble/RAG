import { useState, useEffect } from 'react';
import { useAuthStore } from '../../store/authStore';

interface ActiveUser {
  id: string;
  username: string;
  avatar: string;
}

interface ProjectPresenceProps {
  projectId: string;
  activeTab?: string;
  activeLegalSubTab?: string;
  isGenerating?: boolean;
}

export default function ProjectPresence({ projectId, activeTab, activeLegalSubTab, isGenerating }: ProjectPresenceProps) {
  const [activeUsers, setActiveUsers] = useState<ActiveUser[]>([]);
  const { getAuthHeaders } = useAuthStore();
  const API_BASE = import.meta.env.VITE_API_BASE || '';

  useEffect(() => {
    if (!projectId) return;

    let isMounted = true;

    const reportPresence = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/projects/${projectId}/presence`, {
          method: 'POST',
          headers: {
            ...getAuthHeaders(),
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            active_tab: activeTab || '',
            active_sub_tab: activeLegalSubTab || '',
            is_generating: !!isGenerating
          })
        });
        if (res.ok && isMounted) {
          const data = await res.json();
          // Sort or truncate to max 5 users maybe
          setActiveUsers(data.active_users || []);
        }
      } catch (err) {
        // Silently fail if network is down
      }
    };

    // Immediate report
    reportPresence();

    // Poll every 30 seconds
    const interval = setInterval(reportPresence, 30000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [projectId, activeTab, activeLegalSubTab, isGenerating, getAuthHeaders, API_BASE]);

  if (activeUsers.length === 0) return null;

  return (
    <div className="flex items-center mx-4 gap-2">
      <div className="flex -space-x-2 overflow-hidden py-1">
        {activeUsers.map((u, i) => {
          const zIndex = 10 - i;
          return (
            <div
              key={u.id}
              className="inline-block h-6 w-6 rounded-full ring-2 ring-white bg-indigo-100 flex items-center justify-center text-xs font-medium text-indigo-700 shadow-sm relative"
              style={{ zIndex }}
              title={`${u.username} 正在查看此项目`}
            >
              {u.avatar ? (
                <img
                  src={`${API_BASE}${u.avatar}`}
                  alt={u.username}
                  className="h-full w-full rounded-full object-cover"
                />
              ) : (
                u.username.substring(0, 1).toUpperCase()
              )}
            </div>
          );
        })}
      </div>
      <span className="text-[10px] text-gray-500 whitespace-nowrap">正在浏览</span>
    </div>
  );
}
