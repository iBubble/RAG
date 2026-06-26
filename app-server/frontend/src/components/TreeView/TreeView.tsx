import { useEffect, useState, useRef, useMemo } from 'react';
import { useProjectStore } from '../../store/projectStore';
import { useAuthStore } from '../../store/authStore';
import { FileText, FileSpreadsheet, FileImage, FileVideo, FileAudio, FileQuestion, Loader2, CheckSquare, Square, Folder, FolderOpen, Trash2, Download } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || '';

interface FileItem {
  id: string;
  filename: string;
  path: string;
  size: number;
  source_type?: string;  // web / text / undefined(本地文件)
  source_url?: string;
  chunks?: number;
  library_id?: string;   // 公共文档所属库 ID
  is_public?: boolean;   // 是否为公共文档引用
  ingest_status?: string;
  error_message?: string;
}

interface TreeViewProps {
  projectId: string;
  onFileClick?: (file: FileItem) => void;
  canWrite?: boolean;
}

// 树形节点结构定义
interface TreeNode {
  name: string;
  isFolder: boolean;
  file?: FileItem;
  children: { [key: string]: TreeNode };
}

const renderFileIcon = (file: FileItem) => {
  if (file.source_type === 'web') {
    return (
      <div className="p-1 rounded-md shrink-0 flex items-center justify-center bg-sky-50 text-sky-600 border border-sky-100 dark:bg-sky-950/30 dark:text-sky-400 dark:border-sky-900/50" title="网页来源">
        <span className="w-3.5 h-3.5 text-center leading-3.5 text-[10px] font-bold">🌐</span>
      </div>
    );
  }
  if (file.source_type === 'text') {
    return (
      <div className="p-1 rounded-md shrink-0 flex items-center justify-center bg-indigo-50 text-indigo-600 border border-indigo-100 dark:bg-indigo-950/30 dark:text-indigo-400 dark:border-indigo-900/50" title="粘贴文本">
        <span className="w-3.5 h-3.5 text-center leading-3.5 text-[10px] font-bold">📋</span>
      </div>
    );
  }

  const isFailed = file.ingest_status === 'failed' || file.ingest_status === 'unsupported_format';
  if (isFailed) {
    return (
      <div 
        className="p-1 rounded-md shrink-0 flex items-center justify-center bg-rose-50 text-rose-500 border border-rose-100 dark:bg-rose-950/20 dark:text-rose-400 dark:border-rose-900/30 animate-pulse"
        title={file.ingest_status === 'unsupported_format' ? '格式待支持：此文件格式暂不支持解析向量化' : `解析失败：${file.error_message || '未知异常，请点击重试'}`}
      >
        <FileQuestion className="w-3.5 h-3.5" />
      </div>
    );
  }

  const name = file.filename.toLowerCase();
  
  if (name.endsWith('.mp3') || name.endsWith('.wav') || name.endsWith('.m4a')) {
    return (
      <div className="p-1 rounded-md shrink-0 flex items-center justify-center bg-violet-50 text-violet-600 border border-violet-100 dark:bg-violet-950/30 dark:text-violet-400 dark:border-violet-900/50" title="音频文件">
        <FileAudio className="w-3.5 h-3.5" />
      </div>
    );
  }
  
  if (name.endsWith('.mp4') || name.endsWith('.mov') || name.endsWith('.webm') || name.endsWith('.ogg')) {
    return (
      <div className="p-1 rounded-md shrink-0 flex items-center justify-center bg-amber-50 text-amber-600 border border-amber-100 dark:bg-amber-950/30 dark:text-amber-400 dark:border-amber-900/50" title="视频文件">
        <FileVideo className="w-3.5 h-3.5" />
      </div>
    );
  }

  if (name.endsWith('.xlsx') || name.endsWith('.xls') || name.endsWith('.csv')) {
    return (
      <div className="p-1 rounded-md shrink-0 flex items-center justify-center bg-emerald-50 text-emerald-600 border border-emerald-100 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-900/50" title="电子表格">
        <FileSpreadsheet className="w-3.5 h-3.5" />
      </div>
    );
  }

  if (name.endsWith('.png') || name.endsWith('.jpg') || name.endsWith('.jpeg') || name.endsWith('.webp') || name.endsWith('.svg') || name.endsWith('.bmp') || name.endsWith('.gif')) {
    return (
      <div className="p-1 rounded-md shrink-0 flex items-center justify-center bg-teal-50 text-teal-600 border border-teal-100 dark:bg-teal-950/30 dark:text-teal-400 dark:border-teal-900/50" title="图像文件">
        <FileImage className="w-3.5 h-3.5" />
      </div>
    );
  }

  if (name.endsWith('.pdf')) {
    return (
      <div className="p-1 rounded-md shrink-0 flex items-center justify-center bg-red-50 text-red-600 border border-red-100 dark:bg-red-950/30 dark:text-red-400 dark:border-red-900/50" title="PDF文档">
        <FileText className="w-3.5 h-3.5" />
      </div>
    );
  }

  if (name.endsWith('.docx') || name.endsWith('.doc')) {
    return (
      <div className="p-1 rounded-md shrink-0 flex items-center justify-center bg-blue-50 text-blue-600 border border-blue-100 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-900/50" title="Word文档">
        <FileText className="w-3.5 h-3.5" />
      </div>
    );
  }

  return (
    <div className="p-1 rounded-md shrink-0 flex items-center justify-center bg-gray-50 text-gray-500 border border-gray-200 dark:bg-gray-900/30 dark:text-gray-400 dark:border-gray-800/50" title="文本文档">
      <FileText className="w-3.5 h-3.5" />
    </div>
  );
};

export default function TreeView({ projectId, onFileClick, canWrite = true }: TreeViewProps) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [showConfirmFile, setShowConfirmFile] = useState<FileItem | null>(null);
  const [showConfirmFolder, setShowConfirmFolder] = useState<{ pathKey: string; folderName: string; fileCount: number } | null>(null);
  const [showConfirmBulkDelete, setShowConfirmBulkDelete] = useState(false);
  const [showConfirmExcludeFile, setShowConfirmExcludeFile] = useState<FileItem | null>(null);
  const [showConfirmBulkExclude, setShowConfirmBulkExclude] = useState(false);
  
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [refFiles, setRefFiles] = useState<FileItem[]>([]);
  const [usePublicRef, setUsePublicRef] = useState<boolean>(true);

  const { checkedFileIds, toggleFileCheck, setCheckedFiles, activePreviewFile, setActivePreviewFile, refreshCounter, checkedRefIds, setCheckedRefIds } = useProjectStore();
  const { getAuthHeaders } = useAuthStore();
  const seenFileIdsRef = useRef<Set<string>>(new Set());
  const knownFoldersRef = useRef<Set<string>>(new Set());
  const hasLoadedSavedFoldersRef = useRef<boolean>(false);

  const fetchFiles = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/files/list?project_id=${projectId}`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        const filesList: FileItem[] = data.files || [];
        setFiles(filesList);
        
        // 自动勾选逻辑（左侧默认勾选全部新文件）
        const currentChecked = [...useProjectStore.getState().checkedFileIds];
        let hasNewFiles = false;
        
        filesList.forEach(file => {
          if (!seenFileIdsRef.current.has(file.id)) {
            seenFileIdsRef.current.add(file.id);
            currentChecked.push(file.id);
            hasNewFiles = true;
          }
        });
        
        if (hasNewFiles) {
          setCheckedFiles(currentChecked);
        }
      }
    } catch (e) {
      console.error('获取文件列表失败', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setCheckedFiles([]);
    seenFileIdsRef.current.clear();
    knownFoldersRef.current.clear();
    hasLoadedSavedFoldersRef.current = false;

    // 从 localStorage 中恢复已有的文件展开/收拢状态
    const saved = localStorage.getItem(`project_expanded_folders_${projectId}`);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          setExpandedFolders(new Set(parsed));
          hasLoadedSavedFoldersRef.current = true;
        } else {
          setExpandedFolders(new Set());
        }
      } catch {
        setExpandedFolders(new Set());
      }
    } else {
      setExpandedFolders(new Set());
    }

    fetchFiles();
    const timer = setInterval(fetchFiles, 5000);
    return () => clearInterval(timer);
  }, [projectId]);

  // 监听展开状态的改变并持久化到 localStorage 中
  useEffect(() => {
    if (projectId) {
      localStorage.setItem(
        `project_expanded_folders_${projectId}`,
        JSON.stringify(Array.from(expandedFolders))
      );
    }
  }, [expandedFolders, projectId]);

  // 加载引用的公共文档文件列表
  const fetchRefFiles = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/projects/${projectId}/ref-files`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        setRefFiles(data.files || []);
      }
    } catch (e) {
      console.error('获取公共文档引用失败', e);
    }
  };

  // 联动逻辑：当 usePublicRef 状态或引用的公共文件列表 refFiles 变化时，同步更新选中的 checkedRefIds
  useEffect(() => {
    if (usePublicRef) {
      const allIds = refFiles.map(f => f.id);
      const currentIds = useProjectStore.getState().checkedRefIds;
      const isSame = allIds.length === currentIds.length && allIds.every(id => currentIds.includes(id));
      if (!isSame) {
        setCheckedRefIds(allIds);
      }
    } else {
      const currentIds = useProjectStore.getState().checkedRefIds;
      if (currentIds.length > 0) {
        setCheckedRefIds([]);
      }
    }
  }, [usePublicRef, refFiles, setCheckedRefIds]);

  // WHY: 组件加载 / projectId 变化 / 上传弹窗关闭(refreshCounter) 时均刷新引用列表，
  //       确保数量始终正确。
  useEffect(() => {
    fetchFiles();
    fetchRefFiles();
  }, [projectId, refreshCounter]);

  // 删除文件：触发自定义确认弹窗
  const handleDeleteFileClick = (file: FileItem, e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    setShowConfirmFile(file);
  };

  // 真正执行删除文件逻辑
  const executeDeleteFile = async (file: FileItem) => {
    setShowConfirmFile(null);
    setDeletingId(file.id);
    const isWebSource = file.source_type === 'web' || file.source_type === 'text';
    try {
      let res: Response;
      if (isWebSource) {
        res = await fetch(
          `${API_BASE}/api/web-ingest/${file.id}?project_id=${encodeURIComponent(projectId)}`,
          { method: 'DELETE', headers: getAuthHeaders() }
        );
      } else {
        res = await fetch(
          `${API_BASE}/api/files/delete?file_path=${encodeURIComponent(file.path)}&project_id=${encodeURIComponent(projectId)}`,
          { method: 'DELETE', headers: getAuthHeaders() }
        );
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      setFiles(prev => prev.filter(f => f.id !== file.id));
      setCheckedFiles(checkedFileIds.filter(id => id !== file.id));
      seenFileIdsRef.current.delete(file.id);

      if (activePreviewFile?.id === file.id) {
        setActivePreviewFile(null);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '未知错误';
      alert(`删除失败: ${msg}`);
    } finally {
      setDeletingId(null);
    }
  };

  // 删除文件夹：触发自定义确认弹窗
  const handleDeleteFolderClick = (folderPath: string, folderName: string, fileCount: number, e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    setShowConfirmFolder({ pathKey: folderPath, folderName, fileCount });
  };

  // 真正执行删除文件夹逻辑
  const executeDeleteFolder = async (folderPath: string, folderName: string) => {
    setShowConfirmFolder(null);
    console.log(`正在删除文件夹: ${folderName}`);
    const fullFolderPath = `${projectId}/${folderPath}`;
    setDeletingId(folderPath);
    try {
      const res = await fetch(
        `${API_BASE}/api/files/delete-folder?folder_path=${encodeURIComponent(fullFolderPath)}&project_id=${encodeURIComponent(projectId)}`,
        { method: 'DELETE', headers: getAuthHeaders() }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const removedIds = files
        .filter(f => f.path.startsWith(fullFolderPath + '/') || f.path.startsWith(folderPath + '/'))
        .map(f => f.id);
      setFiles(prev => prev.filter(f => !removedIds.includes(f.id)));
      setCheckedFiles(checkedFileIds.filter(id => !removedIds.includes(id)));
      removedIds.forEach(id => seenFileIdsRef.current.delete(id));

      // 如果正在预览的文件在被删文件夹内，关闭预览
      if (activePreviewFile && removedIds.includes(activePreviewFile.id)) {
        setActivePreviewFile(null);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '未知错误';
      alert(`删除文件夹失败: ${msg}`);
    } finally {
      setDeletingId(null);
    }
  };

  // 从扁平文件列表构建树形目录结构
  const treeRoot = useMemo(() => {
    const root: TreeNode = { name: 'root', isFolder: true, children: {} };
    files.forEach(file => {
      let relPath = file.path;
      if (relPath.startsWith(`${projectId}/`)) {
        relPath = relPath.substring(projectId.length + 1);
      }
      const parts = relPath.split('/');
      let current = root;
      let currentPath = '';

      for (let i = 0; i < parts.length - 1; i++) {
        const part = parts[i];
        currentPath = currentPath ? `${currentPath}/${part}` : part;
        if (!current.children[part]) {
          current.children[part] = { name: part, isFolder: true, children: {} };
        }
        current = current.children[part];
      }
      const fileName = parts[parts.length - 1];
      current.children[fileName] = { name: fileName, isFolder: false, file, children: {} };
    });
    return root;
  }, [files, projectId]);

  // 渲染后将真正新创建的文件夹自动加入展开集合，保留用户手动折叠的状态
  useEffect(() => {
    const allFolders = new Set<string>();
    const collectFolders = (node: TreeNode, currentPath: string = '') => {
      Object.values(node.children).forEach(child => {
        if (child.isFolder) {
          const pathKey = currentPath ? `${currentPath}/${child.name}` : child.name;
          allFolders.add(pathKey);
          collectFolders(child, pathKey);
        }
      });
    };
    collectFolders(treeRoot);
    
    // 如果是从 localStorage 恢复状态后的第一次渲染
    if (hasLoadedSavedFoldersRef.current) {
      // 此时列表中已有的所有文件夹路径均标记为已处理，后续仅新增文件夹会自动展开
      allFolders.forEach(f => knownFoldersRef.current.add(f));
      hasLoadedSavedFoldersRef.current = false;
      return;
    }

    // 找出哪些文件夹是全新出现的（之前不在 knownFoldersRef 中）
    const newlyAddedFolders: string[] = [];
    allFolders.forEach(f => {
      if (!knownFoldersRef.current.has(f)) {
        newlyAddedFolders.push(f);
        knownFoldersRef.current.add(f);
      }
    });

    // 如果有全新文件夹，把它们加入 expandedFolders 中展开
    if (newlyAddedFolders.length > 0) {
      setExpandedFolders(prev => {
        const next = new Set(prev);
        newlyAddedFolders.forEach(f => next.add(f));
        return next;
      });
    }
    
    // 清理已不存在的文件夹缓存
    knownFoldersRef.current.forEach(f => {
      if (!allFolders.has(f)) {
        knownFoldersRef.current.delete(f);
      }
    });
  }, [treeRoot]);

  // 获得一个节点（包括其后代）所有的文件ID
  const getFileIdsUnderNode = (node: TreeNode): string[] => {
    let ids: string[] = [];
    if (!node.isFolder && node.file) {
      ids.push(node.file.id);
    } else {
      Object.values(node.children).forEach(child => {
        ids = ids.concat(getFileIdsUnderNode(child));
      });
    }
    return ids;
  };

  if (loading) {
    return (
      <div className="flex justify-center py-4">
        <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
      </div>
    );
  }

  if (files.length === 0) {
    return <div className="text-gray-400 text-center mt-4">暂无文件，请上传</div>;
  }

  // 计算全局全选状态
  const allFilesIds = files.map(f => f.id);
  const allChecked = allFilesIds.length > 0 && allFilesIds.every(id => checkedFileIds.includes(id));
  const someChecked = allFilesIds.some(id => checkedFileIds.includes(id));

  const handleToggleAll = () => {
    if (allChecked) {
      setCheckedFiles([]);
    } else {
      setCheckedFiles(allFilesIds);
    }
  };

  const toggleFolderExpand = (folderPath: string) => {
    setExpandedFolders(prev => {
      const next = new Set(prev);
      if (next.has(folderPath)) {
        next.delete(folderPath);
      } else {
        next.add(folderPath);
      }
      return next;
    });
  };

  const handleNodeCheck = (node: TreeNode, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!node.isFolder && node.file) {
      toggleFileCheck(node.file.id);
    } else {
      const ids = getFileIdsUnderNode(node);
      const allNodeChecked = ids.length > 0 && ids.every(id => checkedFileIds.includes(id));
      if (allNodeChecked) {
        // 反选这些 IDs
        setCheckedFiles(checkedFileIds.filter(id => !ids.includes(id)));
      } else {
        // 勾选所有缺失的 IDs
        const newChecked = new Set([...checkedFileIds, ...ids]);
        setCheckedFiles(Array.from(newChecked));
      }
    }
  };

  const handleBulkDeleteClick = () => {
    if (checkedFileIds.length === 0) return;
    setShowConfirmBulkDelete(true);
  };

  const executeBulkDelete = async () => {
    setShowConfirmBulkDelete(false);
    if (checkedFileIds.length === 0) return;
    
    const filesToDelete = files.filter(f => checkedFileIds.includes(f.id));
    setDeletingId('bulk-deleting');
    let successCount = 0;
    
    for (const file of filesToDelete) {
      const isWebSource = file.source_type === 'web' || file.source_type === 'text';
      try {
        let res: Response;
        if (isWebSource) {
          res = await fetch(
            `${API_BASE}/api/web-ingest/${file.id}?project_id=${encodeURIComponent(projectId)}`,
            { method: 'DELETE', headers: getAuthHeaders() }
          );
        } else {
          res = await fetch(
            `${API_BASE}/api/files/delete?file_path=${encodeURIComponent(file.path)}&project_id=${encodeURIComponent(projectId)}`,
            { method: 'DELETE', headers: getAuthHeaders() }
          );
        }
        if (res.ok) {
          successCount++;
        }
      } catch (err) {
        console.error(`删除文件 ${file.filename} 失败`, err);
      }
    }

    // 重新获取列表
    fetchFiles();
    setCheckedFiles([]);
    setDeletingId(null);
    if (successCount < filesToDelete.length) {
      alert(`批量删除完成，成功: ${successCount}，失败: ${filesToDelete.length - successCount}`);
    }
  };

  // 真正执行单个公共文档排除逻辑
  const executeExcludeFile = async (file: FileItem) => {
    setShowConfirmExcludeFile(null);
    try {
      const res = await fetch(
        `${API_BASE}/api/projects/${projectId}/exclude-ref-files`,
        {
          method: 'POST',
          headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ file_ids: [file.id] }),
        }
      );
      if (res.ok) {
        setRefFiles(prev => prev.filter(f => f.id !== file.id));
        setCheckedRefIds(checkedRefIds.filter(id => id !== file.id));
      } else {
        alert('排除失败，请重试');
      }
    } catch (e) {
      console.error('排除公共文档失败', e);
      alert('排除失败，请重试');
    }
  };

  // 真正执行批量公共文档排除逻辑
  const executeBulkExclude = async () => {
    setShowConfirmBulkExclude(false);
    if (checkedRefIds.length === 0) return;
    try {
      const res = await fetch(
        `${API_BASE}/api/projects/${projectId}/exclude-ref-files`,
        {
          method: 'POST',
          headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ file_ids: checkedRefIds }),
        }
      );
      if (res.ok) {
        setRefFiles(prev => prev.filter(f => !checkedRefIds.includes(f.id)));
        setCheckedRefIds([]);
      } else {
        alert('排除失败，请重试');
      }
    } catch (e) {
      console.error('排除公共文档失败', e);
      alert('排除失败，请重试');
    }
  };

  // 批量下载或单文件/文件夹下载
  const handleDownload = async (paths: string[], defaultFilename: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    if (paths.length === 0) return;
    
    setDownloadingId(paths.length === 1 ? paths[0] : 'bulk-downloading');
    try {
      const res = await fetch(`${API_BASE}/api/files/download-batch`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, paths })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      
      let filename = defaultFilename;
      const contentDisposition = res.headers.get('content-disposition');
      if (contentDisposition) {
        const match = contentDisposition.match(/filename\*=utf-8''(.+)/i);
        if (match && match[1]) {
          filename = decodeURIComponent(match[1]);
        }
      }

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '未知错误';
      alert(`下载失败: ${msg}`);
    } finally {
      setDownloadingId(null);
    }
  };

  // 递归渲染树节点
  const renderTree = (node: TreeNode, depth: number = 0, currentPath: string = '') => {
    // 对子节点排序：文件夹在上，文件在下，然后字母排序
    const sortedChildren = Object.values(node.children).sort((a, b) => {
      if (a.isFolder === b.isFolder) return a.name.localeCompare(b.name);
      return a.isFolder ? -1 : 1;
    });

    return sortedChildren.map((child) => {
      const pathKey = currentPath ? `${currentPath}/${child.name}` : child.name;

      if (child.isFolder) {
        const isExpanded = expandedFolders.has(pathKey);
        const childIds = getFileIdsUnderNode(child);
        const isAllChecked = childIds.length > 0 && childIds.every(id => checkedFileIds.includes(id));
        const isSomeChecked = childIds.some(id => checkedFileIds.includes(id));

        const isDeletingFolder = deletingId === pathKey;

        return (
          <div key={pathKey} className={`flex flex-col ${isDeletingFolder ? 'opacity-50 pointer-events-none' : ''}`}>
            <div
              className="flex items-center gap-1.5 p-1.5 rounded cursor-pointer hover:bg-gray-100 text-gray-700 transition-colors group/folder"
              style={{ paddingLeft: `${depth * 12 + 6}px` }}
              onClick={() => toggleFolderExpand(pathKey)}
            >
              <div 
                className={`mt-0.5 shrink-0 ${isSomeChecked ? 'text-blue-500' : 'text-gray-300'}`}
                onClick={(e) => handleNodeCheck(child, e)}
              >
                {isAllChecked ? (
                  <CheckSquare className="w-3.5 h-3.5" />
                ) : isSomeChecked ? (
                  <CheckSquare className="w-3.5 h-3.5 opacity-50" />
                ) : (
                  <Square className="w-3.5 h-3.5" />
                )}
              </div>
              
              <div className="flex items-center gap-1 flex-1 min-w-0 text-gray-600 group-hover/folder:text-blue-600 transition-colors">
                {isExpanded ? <FolderOpen className="w-4 h-4 opacity-80 shrink-0" /> : <Folder className="w-4 h-4 opacity-80 shrink-0" />}
                <span className="text-sm font-medium truncate select-none">{child.name}</span>
                <span className="text-[10px] text-gray-400 shrink-0">({childIds.length})</span>
              </div>

              {/* 文件夹悬浮下载与删除按钮 */}
              <div className="flex items-center gap-1 opacity-0 group-hover/folder:opacity-100 transition-opacity">
                <button
                  className="p-0.5 rounded hover:bg-blue-100 text-gray-300 hover:text-blue-500"
                  title={`下载文件夹 ${child.name}`}
                  onClick={(e) => handleDownload([`${projectId}/${pathKey}`], `${child.name}.zip`, e)}
                  disabled={downloadingId === `${projectId}/${pathKey}`}
                >
                  {downloadingId === `${projectId}/${pathKey}` ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
                  ) : (
                    <Download className="w-3.5 h-3.5" />
                  )}
                </button>
                {canWrite && (
                  <button
                    className="p-0.5 rounded hover:bg-red-100 text-gray-300 hover:text-red-500"
                    title={`删除文件夹 ${child.name}（含 ${childIds.length} 个文件）`}
                    onMouseDown={(e) => e.stopPropagation()}
                    onClick={(e) => handleDeleteFolderClick(pathKey, child.name, childIds.length, e)}
                  >
                    {isDeletingFolder ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="w-3.5 h-3.5" />
                    )}
                  </button>
                )}
              </div>
            </div>
            {isExpanded && (
              <div className="flex flex-col">
                {renderTree(child, depth + 1, pathKey)}
              </div>
            )}
          </div>
        );
      }

      // 文件节点
      const file = child.file!;
      const isChecked = checkedFileIds.includes(file.id);
      const isActive = activePreviewFile?.id === file.id;
      const isDeleting = deletingId === file.id;

      return (
         <div
            key={file.id}
            className={`flex items-start gap-1 p-1.5 rounded cursor-pointer transition-colors group/file ${
              isActive ? 'bg-blue-100 text-blue-800 ring-1 ring-blue-300' :
              isChecked ? 'bg-blue-50 text-blue-700' : 'hover:bg-gray-50 text-gray-700'
            } ${isDeleting ? 'opacity-50 pointer-events-none' : ''}`}
            style={{ paddingLeft: `${depth * 12 + 6}px` }}
          >
            <div
              className="mt-0.5 text-blue-500 shrink-0"
              onClick={(e) => handleNodeCheck(child, e)}
            >
              {isChecked ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4 text-gray-300" />}
            </div>

            <div
              className="flex items-start gap-1.5 flex-1 min-w-0 ml-0.5"
              onClick={() => onFileClick?.(file)}
            >
              {renderFileIcon(file)}
              <div className="flex-1 min-w-0">
                <div className="truncate text-sm" title={file.filename}>
                  {file.filename}
                </div>
                <div className="text-[10px] text-gray-400">
                  {file.source_type === 'web' || file.source_type === 'text'
                    ? `${file.size} 字 · ${file.chunks || 0} chunks`
                    : `${(file.size / 1024).toFixed(1)} KB`
                  }
                </div>
              </div>
            </div>

            {/* 悬浮下载与删除按钮 */}
            <div className="flex items-center gap-1 mt-0.5 opacity-0 group-hover/file:opacity-100 transition-opacity">
              <button
                className="p-0.5 rounded hover:bg-blue-100 text-gray-300 hover:text-blue-500"
                title={`下载 ${file.filename}`}
                onClick={(e) => handleDownload([file.path], file.filename, e)}
                disabled={downloadingId === file.path}
              >
                {downloadingId === file.path ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
                ) : (
                  <Download className="w-3.5 h-3.5" />
                )}
              </button>
              {canWrite && (
                <button
                  className="p-0.5 rounded hover:bg-red-100 text-gray-300 hover:text-red-500"
                  title={`删除 ${file.filename}`}
                  onMouseDown={(e) => e.stopPropagation()}
                  onClick={(e) => handleDeleteFileClick(file, e)}
                >
                  {isDeleting ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="w-3.5 h-3.5" />
                  )}
                </button>
              )}
            </div>
          </div>
      );
    });
  };

  return (
    <div className="flex flex-col gap-2">
      {/* 引用所有公共文档 */}
      {refFiles.length > 0 && (
        <div className="flex items-center justify-between p-2 mb-1 bg-[#F7F5F0] border border-[#E0DCD5] rounded-md shadow-sm">
          <div 
            className="flex items-center gap-2 cursor-pointer group select-none"
            onClick={() => setUsePublicRef(!usePublicRef)}
          >
            <div className={`shrink-0 transition-colors ${usePublicRef ? 'text-[#8B7355]' : 'text-gray-400 group-hover:text-[#8B7355]'}`}>
              {usePublicRef ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
            </div>
            <span className={`text-xs font-semibold transition-colors ${usePublicRef ? 'text-[#8B7355]' : 'text-gray-500 group-hover:text-gray-700'}`}>
              引用所有公共文档 ({refFiles.length}个)
            </span>
          </div>
        </div>
      )}

      <>
          {/* 顶部工具栏：全选与选中统计 */}
          <div className="flex items-center justify-between pb-2 border-b border-gray-100 px-1 flex-nowrap gap-1">
             <div 
               className="flex items-center gap-1.5 cursor-pointer group shrink-0"
               onClick={handleToggleAll}
             >
               <div className={`mt-0.5 shrink-0 ${someChecked ? 'text-blue-500' : 'text-gray-300'}`}>
                 {allChecked ? <CheckSquare className="w-4 h-4 group-hover:opacity-80" /> : <Square className="w-4 h-4 group-hover:text-blue-400" />}
               </div>
               <span className="text-sm font-medium text-gray-700 group-hover:text-blue-600 transition-colors whitespace-nowrap">
                   全选({checkedFileIds.length}/{files.length})
               </span>
             </div>
             
             <div className="flex items-center gap-1 shrink-0">
               {checkedFileIds.length > 0 && (
                 <button
                   onClick={() => handleDownload(
                     files.filter(f => checkedFileIds.includes(f.id)).map(f => f.path),
                     `批量下载_${checkedFileIds.length}个文件.zip`
                   )}
                   disabled={downloadingId === 'bulk-downloading'}
                   className="text-xs text-blue-500 font-medium hover:bg-blue-50 px-1.5 py-1 rounded flex items-center gap-0.5 transition-colors whitespace-nowrap"
                 >
                   {downloadingId === 'bulk-downloading' ? (
                     <Loader2 className="w-3 h-3 animate-spin" />
                   ) : (
                     <Download className="w-3 h-3" />
                   )}
                    下载({checkedFileIds.length})
                 </button>
               )}
               {canWrite && checkedFileIds.length > 0 && (
                 <button
                    onClick={handleBulkDeleteClick}
                   disabled={deletingId === 'bulk-deleting'}
                   className="text-xs text-red-500 font-medium hover:bg-red-50 px-1.5 py-1 rounded flex items-center gap-0.5 transition-colors whitespace-nowrap"
                 >
                   {deletingId === 'bulk-deleting' ? (
                     <Loader2 className="w-3 h-3 animate-spin" />
                   ) : (
                     <Trash2 className="w-3 h-3" />
                   )}
                    删除({checkedFileIds.length})
                 </button>
               )}
             </div>
          </div>

          {/* 结构树渲染区 */}
          <div className="space-y-0.5 pb-4">
            {renderTree(treeRoot)}
          </div>
        </>

      {/* 自定义确认弹窗组件列表 */}
      <ConfirmModal
        isOpen={!!showConfirmFile}
        title="确认删除该文件吗？"
        message={`您确定要删除文件「${showConfirmFile?.filename || ''}」吗？\n\n此操作将同时清除该文件在知识库中的向量索引，删除后不可恢复。`}
        onConfirm={() => showConfirmFile && executeDeleteFile(showConfirmFile)}
        onCancel={() => setShowConfirmFile(null)}
        confirmText="确认删除"
      />

      <ConfirmModal
        isOpen={!!showConfirmFolder}
        title="确认删除该文件夹吗？"
        message={`您确定要删除文件夹「${showConfirmFolder?.folderName || ''}」吗？\n\n该文件夹下的共 ${showConfirmFolder?.fileCount || 0} 个文件将被永久删除，且关联的知识库向量索引也将被清除。此操作不可恢复。`}
        onConfirm={() => showConfirmFolder && executeDeleteFolder(showConfirmFolder.pathKey, showConfirmFolder.folderName)}
        onCancel={() => setShowConfirmFolder(null)}
        confirmText="确认删除"
      />

      <ConfirmModal
        isOpen={showConfirmBulkDelete}
        title="确认批量删除文件吗？"
        message={`您确定要删除已选中的 ${files.filter(f => checkedFileIds.includes(f.id)).length} 个文件吗？\n\n此操作将同步清除这些文件在知识库中的向量索引。此操作不可恢复。`}
        onConfirm={executeBulkDelete}
        onCancel={() => setShowConfirmBulkDelete(false)}
        confirmText="确认批量删除"
      />

      <ConfirmModal
        isOpen={!!showConfirmExcludeFile}
        title="取消公共文档引用吗？"
        message={`您确定要取消引用公共文档「${showConfirmExcludeFile?.filename || ''}」吗？\n\n此操作仅会移除本案件与该公共文档的引用关系，不会删除公共文档库中的原始文件。`}
        onConfirm={() => showConfirmExcludeFile && executeExcludeFile(showConfirmExcludeFile)}
        onCancel={() => setShowConfirmExcludeFile(null)}
        confirmText="取消引用"
        type="warning"
      />

      <ConfirmModal
        isOpen={showConfirmBulkExclude}
        title="批量取消公共文档引用吗？"
        message={`您确定要取消引用选中的这 ${checkedRefIds.length} 个公共文档吗？\n\n此操作仅会移除引用关系，不会删除公共文档库中的原始文件。`}
        onConfirm={executeBulkExclude}
        onCancel={() => setShowConfirmBulkExclude(false)}
        confirmText="取消引用"
        type="warning"
      />
    </div>
  );
}

interface ConfirmModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmText?: string;
  cancelText?: string;
  type?: 'danger' | 'warning';
}

function ConfirmModal({
  isOpen,
  title,
  message,
  onConfirm,
  onCancel,
  confirmText = '确定',
  cancelText = '取消',
  type = 'danger'
}: ConfirmModalProps) {
  if (!isOpen) return null;
  const isDanger = type === 'danger';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div 
        className="absolute inset-0 bg-[#0F0F11]/45 backdrop-blur-[2px] transition-opacity" 
        onClick={onCancel}
      />
      <div className="relative bg-white rounded-xl p-5 shadow-xl border border-gray-100 max-w-sm w-full flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-start gap-3">
          <div className={`p-2 rounded-full shrink-0 ${isDanger ? 'bg-red-50 text-red-600' : 'bg-amber-50 text-amber-600'}`}>
            <Trash2 className="w-4 h-4" />
          </div>
          <div className="flex flex-col gap-1 min-w-0">
            <h3 className="text-sm font-semibold text-gray-900 leading-none">{title}</h3>
            <p className="text-xs text-gray-500 leading-normal mt-2 whitespace-pre-wrap">{message}</p>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-2">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 text-xs font-medium text-gray-600 hover:text-gray-800 hover:bg-gray-50 rounded-lg transition-colors border border-gray-200"
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            className={`px-3 py-1.5 text-xs font-medium text-white rounded-lg transition-colors shadow-sm ${
              isDanger 
                ? 'bg-red-600 hover:bg-red-700 active:bg-red-800' 
                : 'bg-amber-600 hover:bg-amber-700 active:bg-amber-800'
            }`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
