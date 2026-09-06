import { useEffect, useState, useRef, useMemo } from 'react';
import { useProjectStore } from '../../store/projectStore';
import { useAuthStore } from '../../store/authStore';
import { FileText, FileSpreadsheet, FileImage, FileVideo, FileAudio, FileQuestion, Loader2, CheckSquare, Square, Folder, FolderOpen, Trash2, Download, FolderPlus, MoveRight, X } from 'lucide-react';

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
  isRef?: boolean;
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
      <div className="p-1 rounded-md shrink-0 flex items-center justify-center bg-indigo-50 text-indigo-600 border border-indigo-100 dark:bg-indigo-950/30 dark:text-indigo-400 dark:border-indigo-900/50" title="新建文本">
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
  const [directories, setDirectories] = useState<string[]>([]);
  const [showCreateFolderModal, setShowCreateFolderModal] = useState(false);
  const [newFolderParent, setNewFolderParent] = useState('');
  const [newFolderName, setNewFolderName] = useState('');
  const [isCreatingFolder, setIsCreatingFolder] = useState(false);
  
  const [showMoveModal, setShowMoveModal] = useState(false);
  const [targetMoveFolder, setTargetMoveFolder] = useState('');
  const [isMovingFiles, setIsMovingFiles] = useState(false);

  const [refFiles, setRefFiles] = useState<FileItem[]>([]);
  const [usePublicRef, setUsePublicRef] = useState<boolean>(true);
  const [projectRefFiles, setProjectRefFiles] = useState<FileItem[]>([]);


  const { checkedFileIds, toggleFileCheck, setCheckedFiles, activePreviewFile, setActivePreviewFile, refreshCounter, checkedRefIds, setCheckedRefIds, setProjectFiles } = useProjectStore();
  const { getAuthHeaders } = useAuthStore();
  const seenFileIdsRef = useRef<Set<string>>(new Set());

  const fetchFiles = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/files/list?project_id=${projectId}`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        const filesList: FileItem[] = data.files || [];
        setFiles(filesList);
        setProjectFiles(filesList);
        if (data.directories && Array.isArray(data.directories)) {
          setDirectories(data.directories);
        }
        
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
    // 目录默认全部折叠，清理历史旧缓存中被污染的全量展开数据
    localStorage.removeItem(`project_expanded_folders_${projectId}`);
    setExpandedFolders(new Set());

    fetchFiles();
    const timer = setInterval(fetchFiles, 5000);
    return () => clearInterval(timer);
  }, [projectId, refreshCounter]);

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

  // 加载手工引用的其他公开项目文档列表
  const fetchProjectRefFiles = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/projects/${projectId}/project-ref-files`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        setProjectRefFiles(data.files || []);
      }
    } catch (e) {
      console.error('获取关联公开项目文档失败', e);
    }
  };

  // 联动逻辑：同步公共文档的全选/全反选状态到 checkedRefIds
  useEffect(() => {
    const publicIds = refFiles.map(f => f.id);
    const currentIds = useProjectStore.getState().checkedRefIds;
    
    if (usePublicRef) {
      const newChecked = Array.from(new Set([...currentIds, ...publicIds]));
      setCheckedRefIds(newChecked);
    } else {
      const newChecked = currentIds.filter(id => !publicIds.includes(id));
      setCheckedRefIds(newChecked);
    }
  }, [usePublicRef, refFiles, setCheckedRefIds]);

  // 当项目 ID 发生改变时，重置 usePublicRef 状态并清空所有勾选，防止交叉污染
  useEffect(() => {
    setUsePublicRef(true);
    setCheckedRefIds([]);
  }, [projectId, setCheckedRefIds]);

  // WHY: 组件加载 / projectId 变化 / 上传弹窗关闭(refreshCounter) 时均刷新引用列表，
  //       确保数量始终正确。
  useEffect(() => {
    fetchFiles();
    fetchRefFiles();
    fetchProjectRefFiles();
  }, [projectId, refreshCounter]);

  // 删除文件：触发自定义确认弹窗
  const handleDeleteFileClick = (file: FileItem, e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    const isReferencedFile = file.isRef || projectRefFiles.some(f => f.id === file.id);
    if (isReferencedFile) {
      setShowConfirmExcludeFile(file);
    } else {
      setShowConfirmFile(file);
    }
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
    if (folderName === '其他公开项目文档') {
      setShowConfirmBulkExclude(true);
    } else {
      setShowConfirmFolder({ pathKey: folderPath, folderName, fileCount });
    }
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

  // 新建目录/子目录逻辑
  const handleCreateFolder = async () => {
    const trimmed = newFolderName.trim();
    if (!trimmed) {
      alert('请输入文件夹名称');
      return;
    }
    const fullPath = newFolderParent ? `${newFolderParent}/${trimmed}` : trimmed;
    setIsCreatingFolder(true);
    try {
      const res = await fetch(`${API_BASE}/api/files/create-folder`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          project_id: projectId,
          folder_path: fullPath,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      setExpandedFolders(prev => new Set([...prev, fullPath]));
      setShowCreateFolderModal(false);
      setNewFolderName('');
      await fetchFiles();
    } catch (e: any) {
      alert(`创建目录失败: ${e.message}`);
    } finally {
      setIsCreatingFolder(false);
    }
  };

  // 批量移动选中的文件至指定目录
  const handleBatchMoveFiles = async () => {
    if (checkedFileIds.length === 0) return;
    setIsMovingFiles(true);
    try {
      const res = await fetch(`${API_BASE}/api/files/batch-move`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          project_id: projectId,
          file_ids: checkedFileIds,
          target_folder: targetMoveFolder,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      if (targetMoveFolder) {
        setExpandedFolders(prev => new Set([...prev, targetMoveFolder]));
      }
      setShowMoveModal(false);
      setCheckedFiles([]);
      await fetchFiles();
    } catch (e: any) {
      alert(`移动文件失败: ${e.message}`);
    } finally {
      setIsMovingFiles(false);
    }
  };

  // 从扁平文件列表构建树形目录结构
  const treeRoot = useMemo(() => {
    const root: TreeNode = { name: 'root', isFolder: true, children: {} };

    // 1. 将本项目的本地文件直接放入 root 顶级层级下
    files.forEach(file => {
      let relPath = file.path;
      if (file.source_type === 'web' || file.source_type === 'text') {
        relPath = file.filename;
      } else if (relPath.startsWith(`${projectId}/`)) {
        relPath = relPath.substring(projectId.length + 1);
      }
      const parts = relPath.split('/');
      let current = root;

      for (let i = 0; i < parts.length - 1; i++) {
        const part = parts[i];
        if (!current.children[part]) {
          current.children[part] = { name: part, isFolder: true, children: {} };
        }
        current = current.children[part];
      }
      const fileName = parts[parts.length - 1];
      current.children[fileName] = { name: fileName, isFolder: false, file, children: {} };
    });

    // 2. 将项目所有已知目录结构（包含新建空目录、选定上传的空目录）注入树中
    directories.forEach(dirPath => {
      const parts = dirPath.split('/').filter(Boolean);
      let current = root;
      for (const part of parts) {
        if (!current.children[part]) {
          current.children[part] = { name: part, isFolder: true, children: {} };
        }
        current = current.children[part];
      }
    });

    // 3. 将引用其他项目的文档塞入“其他公开项目文档”虚拟顶级文件夹下
    if (projectRefFiles.length > 0) {
      const refFolderName = '其他公开项目文档';
      root.children[refFolderName] = {
        name: refFolderName,
        isFolder: true,
        children: {}
      };

      projectRefFiles.forEach(file => {
        root.children[refFolderName].children[file.filename] = {
          name: file.filename,
          isFolder: false,
          file: { ...file, isRef: true },
          children: {}
        };
      });
    }

    return root;
  }, [files, directories, projectRefFiles, projectId]);

  const bulkExcludeCount = useMemo(() => {
    const selectedProjRefIds = projectRefFiles.filter(f => checkedRefIds.includes(f.id)).map(f => f.id);
    return selectedProjRefIds.length > 0 ? selectedProjRefIds.length : projectRefFiles.length;
  }, [projectRefFiles, checkedRefIds]);



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

  if (files.length === 0 && refFiles.length === 0 && directories.length === 0 && !canWrite) {
    return <div className="text-gray-400 text-center mt-4">暂无文件，请上传或引用</div>;
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

  // 一键切换全部折叠 / 全部展开
  const toggleExpandAll = () => {
    if (expandedFolders.size > 0) {
      setExpandedFolders(new Set());
    } else {
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
      setExpandedFolders(allFolders);
    }
  };

  const handleNodeCheck = (node: TreeNode, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!node.isFolder && node.file) {
      const isRef = node.file.isRef || projectRefFiles.some(rf => rf.id === node.file?.id);
      if (isRef) {
        if (checkedRefIds.includes(node.file.id)) {
          setCheckedRefIds(checkedRefIds.filter(id => id !== node.file?.id));
        } else {
          setCheckedRefIds([...checkedRefIds, node.file.id]);
        }
      } else {
        toggleFileCheck(node.file.id);
      }
    } else {
      const ids = getFileIdsUnderNode(node);
      const isRef = node.name === '其他公开项目文档' || ids.some(id => projectRefFiles.some(rf => rf.id === id));
      if (isRef) {
        const allNodeChecked = ids.length > 0 && ids.every(id => checkedRefIds.includes(id));
        if (allNodeChecked) {
          setCheckedRefIds(checkedRefIds.filter(id => !ids.includes(id)));
        } else {
          const newChecked = new Set([...checkedRefIds, ...ids]);
          setCheckedRefIds(Array.from(newChecked));
        }
      } else {
        const allNodeChecked = ids.length > 0 && ids.every(id => checkedFileIds.includes(id));
        if (allNodeChecked) {
          setCheckedFiles(checkedFileIds.filter(id => !ids.includes(id)));
        } else {
          const newChecked = new Set([...checkedFileIds, ...ids]);
          setCheckedFiles(Array.from(newChecked));
        }
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

  // 真正执行单个公共/项目文档排除逻辑
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
        setProjectRefFiles(prev => prev.filter(f => f.id !== file.id));
        setCheckedRefIds(checkedRefIds.filter(id => id !== file.id));
      } else {
        alert('排除失败，请重试');
      }
    } catch (e) {
      console.error('排除公共/项目文档失败', e);
      alert('排除失败，请重试');
    }
  };

  // 真正执行批量公开项目文档排除逻辑
  const executeBulkExclude = async () => {
    setShowConfirmBulkExclude(false);
    const projectRefIds = projectRefFiles.map(f => f.id);
    let toExcludeIds = checkedRefIds.filter(id => projectRefIds.includes(id));
    if (toExcludeIds.length === 0) {
      toExcludeIds = projectRefIds;
    }
    if (toExcludeIds.length === 0) return;
    try {
      const res = await fetch(
        `${API_BASE}/api/projects/${projectId}/exclude-ref-files`,
        {
          method: 'POST',
          headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ file_ids: toExcludeIds }),
        }
      );
      if (res.ok) {
        setProjectRefFiles(prev => prev.filter(f => !toExcludeIds.includes(f.id)));
        setCheckedRefIds(checkedRefIds.filter(id => !toExcludeIds.includes(id)));
      } else {
        alert('排除失败，请重试');
      }
    } catch (e) {
      console.error('排除公开项目文档失败', e);
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
        const isRefRoot = child.name === '其他公开项目文档';

        const isExpanded = expandedFolders.has(pathKey);
        const childIds = getFileIdsUnderNode(child);

        // 如果是引用目录，使用 checkedRefIds 进行勾选判断，否则用 checkedFileIds
        const isAllChecked = childIds.length > 0 && childIds.every(id => {
          return isRefRoot || pathKey.startsWith('其他公开项目文档/')
            ? checkedRefIds.includes(id)
            : checkedFileIds.includes(id);
        });
        const isSomeChecked = childIds.some(id => {
          return isRefRoot || pathKey.startsWith('其他公开项目文档/')
            ? checkedRefIds.includes(id)
            : checkedFileIds.includes(id);
        });

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
                <span className={`text-sm ${isRefRoot ? 'font-bold' : 'font-medium'} truncate select-none`}>{child.name}</span>
                <span className="text-[10px] text-gray-400 shrink-0">({childIds.length})</span>
              </div>

              {/* 文件夹悬浮下载与删除按钮 */}
              <div className="flex items-center gap-1 opacity-0 group-hover/folder:opacity-100 transition-opacity">
                {isRefRoot ? (
                  canWrite && (
                    <button
                      className="p-0.5 rounded hover:bg-red-50 text-gray-300 hover:text-red-500 transition-colors"
                      title="取消引用所有公开项目文档"
                      onMouseDown={(e) => e.stopPropagation()}
                      onClick={(e) => {
                        e.stopPropagation();
                        setShowConfirmBulkExclude(true);
                      }}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )
                ) : (
                  <>
                    {canWrite && (
                      <button
                        className="p-0.5 rounded hover:bg-blue-100 text-gray-300 hover:text-blue-600 transition-colors"
                        title={`在「${child.name}」下新建子目录`}
                        onMouseDown={(e) => e.stopPropagation()}
                        onClick={(e) => {
                          e.stopPropagation();
                          setNewFolderParent(pathKey);
                          setNewFolderName('');
                          setShowCreateFolderModal(true);
                        }}
                      >
                        <FolderPlus className="w-3.5 h-3.5" />
                      </button>
                    )}
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
                  </>
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
      const isRef = file.isRef || projectRefFiles.some(rf => rf.id === file.id);
      const isChecked = isRef ? checkedRefIds.includes(file.id) : checkedFileIds.includes(file.id);
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
                  title={isRef ? `取消引用 ${file.filename}` : `删除 ${file.filename}`}
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
        <div className="flex items-center justify-between p-2 mb-1 bg-[#F7F5F0] dark:bg-[#282A31] border border-[#E0DCD5] dark:border-[#2E313A] rounded-md shadow-sm">
          <div 
            className="flex items-center justify-between w-full cursor-pointer select-none"
            onClick={() => setUsePublicRef(!usePublicRef)}
          >
            <span className="text-xs font-semibold text-[#8B7355] dark:text-[#C4B5A0]">
              引用所有公共文档 ({refFiles.length}个)
            </span>
            {/* 极简 iOS 风格滑动开关 */}
            <div 
              className={`relative w-8 h-4.5 rounded-full transition-colors duration-200 shrink-0 ${
                usePublicRef ? 'bg-[#8B7355]' : 'bg-gray-300'
              }`}
            >
              <div 
                className={`absolute top-[2px] left-[2px] w-3.5 h-3.5 rounded-full bg-white transition-transform duration-200 shadow-sm ${
                  usePublicRef ? 'translate-x-3.5' : 'translate-x-0'
                }`}
              />
            </div>
          </div>
        </div>
      )}

      <>
          {/* 顶部工具栏：全选与选中统计 */}
          <div className="flex flex-col gap-1.5 pb-2 border-b border-gray-100">
             {/* 第一行：全选统计、折叠/展开、新建目录 */}
             <div className="flex items-center justify-between px-1 gap-1">
               <div className="flex items-center gap-2">
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

                 <button
                   type="button"
                   onClick={toggleExpandAll}
                   className="text-[11px] text-gray-400 hover:text-blue-600 dark:text-gray-500 dark:hover:text-blue-400 hover:bg-gray-100 dark:hover:bg-gray-800 px-1.5 py-0.5 rounded transition-colors whitespace-nowrap"
                   title={expandedFolders.size > 0 ? "一键折叠所有目录" : "一键展开所有目录"}
                 >
                   {expandedFolders.size > 0 ? "全部折叠" : "全部展开"}
                 </button>
               </div>

               {canWrite && (
                 <button
                   type="button"
                   onClick={() => {
                     setNewFolderParent('');
                     setNewFolderName('');
                     setShowCreateFolderModal(true);
                   }}
                   className="text-[11px] text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/30 px-2 py-1 rounded transition-colors flex items-center gap-1 whitespace-nowrap border border-blue-200/60 shadow-2xs font-medium shrink-0"
                   title="在当前项目新建目录或子目录"
                 >
                   <FolderPlus className="w-3.5 h-3.5" />
                   <span>新建目录</span>
                 </button>
               )}
             </div>

             {/* 第二行：多选批量操作栏（纯文字无数字，精致单行排列） */}
             {checkedFileIds.length > 0 && (
               <div className="flex items-center gap-1.5 px-2 py-1 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200/60 dark:border-gray-700/60 shadow-xs justify-start flex-nowrap overflow-x-auto">
                 {canWrite && (
                   <button
                     onClick={() => {
                       setTargetMoveFolder('');
                       setShowMoveModal(true);
                     }}
                     disabled={isMovingFiles}
                     className="text-xs text-indigo-600 dark:text-indigo-400 font-medium hover:bg-indigo-50 dark:hover:bg-indigo-950/40 px-2 py-1 rounded-md flex items-center gap-1 transition-colors whitespace-nowrap border border-indigo-200/60 bg-white dark:bg-gray-800 shadow-2xs cursor-pointer shrink-0"
                     title={`移动选中的 ${checkedFileIds.length} 个文件到指定目录`}
                   >
                     <MoveRight className="w-3.5 h-3.5" />
                     <span>移动</span>
                   </button>
                 )}
                 <button
                   onClick={() => handleDownload(
                     files.filter(f => checkedFileIds.includes(f.id)).map(f => f.path),
                     `批量下载_${checkedFileIds.length}个文件.zip`
                   )}
                   disabled={downloadingId === 'bulk-downloading'}
                   className="text-xs text-blue-600 dark:text-blue-400 font-medium hover:bg-blue-50 dark:hover:bg-blue-950/40 px-2 py-1 rounded-md flex items-center gap-1 transition-colors whitespace-nowrap border border-blue-200/60 bg-white dark:bg-gray-800 shadow-2xs cursor-pointer"
                 >
                   {downloadingId === 'bulk-downloading' ? (
                     <Loader2 className="w-3.5 h-3.5 animate-spin" />
                   ) : (
                     <Download className="w-3.5 h-3.5" />
                   )}
                   <span>下载</span>
                 </button>
                 {canWrite && (
                   <button
                     onClick={handleBulkDeleteClick}
                     disabled={deletingId === 'bulk-deleting'}
                     className="text-xs text-red-600 dark:text-red-400 font-medium hover:bg-red-50 dark:hover:bg-red-950/40 px-2 py-1 rounded-md flex items-center gap-1 transition-colors whitespace-nowrap border border-red-200/60 bg-white dark:bg-gray-800 shadow-2xs cursor-pointer"
                   >
                     {deletingId === 'bulk-deleting' ? (
                       <Loader2 className="w-3.5 h-3.5 animate-spin" />
                     ) : (
                       <Trash2 className="w-3.5 h-3.5" />
                     )}
                     <span>删除</span>
                   </button>
                 )}
               </div>
             )}
          </div>

          {/* 结构树渲染区 */}
          <div className="space-y-0.5 pb-4">
            {Object.keys(treeRoot.children).length === 0 ? (
              <div className="text-gray-400 text-center py-6 text-xs bg-gray-50/50 rounded-lg border border-dashed border-gray-200 mt-2">
                暂无文件或目录，可点击上方「新建目录」或上传文档
              </div>
            ) : (
              renderTree(treeRoot)
            )}
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
        title="取消项目文档引用吗？"
        message={`您确定要取消引用项目文档「${showConfirmExcludeFile?.filename || ''}」吗？\n\n此操作仅会移除本案件与该项目文档的引用关系，不会删除原项目中的物理文件。`}
        onConfirm={() => showConfirmExcludeFile && executeExcludeFile(showConfirmExcludeFile)}
        onCancel={() => setShowConfirmExcludeFile(null)}
        confirmText="取消引用"
        type="warning"
      />

      <ConfirmModal
        isOpen={showConfirmBulkExclude}
        title="批量取消公开项目文档引用吗？"
        message={`您确定要取消引用这 ${bulkExcludeCount} 个公开项目文档吗？\n\n此操作仅会移除引用关系，不会删除任何原公开项目中的文件。`}
        onConfirm={executeBulkExclude}
        onCancel={() => setShowConfirmBulkExclude(false)}
        confirmText="取消引用"
        type="warning"
      />

      {/* 新建目录弹窗 */}
      {showCreateFolderModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-sm border border-gray-100 dark:border-gray-700 p-5">
            <div className="flex items-center justify-between mb-4 border-b border-gray-100 dark:border-gray-700 pb-2.5">
              <h3 className="font-bold text-gray-800 dark:text-gray-100 text-sm flex items-center gap-1.5">
                <FolderPlus className="w-4 h-4 text-blue-500" />
                新建目录
              </h3>
              <button
                onClick={() => setShowCreateFolderModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">存放位置（父目录）</label>
                <select
                  value={newFolderParent}
                  onChange={(e) => setNewFolderParent(e.target.value)}
                  className="w-full text-xs border border-gray-200 dark:border-gray-600 rounded px-2.5 py-1.5 bg-gray-50 dark:bg-gray-700 text-gray-700 dark:text-gray-200 outline-none focus:border-blue-500"
                >
                  <option value="">/ 根目录（顶级目录）</option>
                  {directories.map(d => (
                    <option key={d} value={d}>📂 {d}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">目录名称</label>
                <input
                  type="text"
                  placeholder="请输入目录名称，如：立案材料、市场监管..."
                  value={newFolderName}
                  onChange={(e) => setNewFolderName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleCreateFolder()}
                  autoFocus
                  className="w-full text-xs border border-gray-200 dark:border-gray-600 rounded px-2.5 py-1.5 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                />
              </div>
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setShowCreateFolderModal(false)}
                className="px-3 py-1.5 text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-100 rounded"
              >
                取消
              </button>
              <button
                onClick={handleCreateFolder}
                disabled={isCreatingFolder || !newFolderName.trim()}
                className="px-3.5 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 text-white font-medium rounded flex items-center gap-1 transition disabled:opacity-50"
              >
                {isCreatingFolder && <Loader2 className="w-3 h-3 animate-spin" />}
                创建
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 批量移动文件弹窗 */}
      {showMoveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-md border border-gray-100 dark:border-gray-700 p-5">
            <div className="flex items-center justify-between mb-4 border-b border-gray-100 dark:border-gray-700 pb-2.5">
              <h3 className="font-bold text-gray-800 dark:text-gray-100 text-sm flex items-center gap-1.5">
                <MoveRight className="w-4 h-4 text-indigo-500" />
                移动选中的 {checkedFileIds.length} 个文件
              </h3>
              <button
                onClick={() => setShowMoveModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            
            <div className="space-y-3">
              <p className="text-xs text-gray-500 dark:text-gray-400">请选择目标目标文件夹：</p>
              <div className="max-h-56 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg p-2 space-y-1 bg-gray-50/50 dark:bg-gray-900/40">
                <div
                  onClick={() => setTargetMoveFolder('')}
                  className={`px-3 py-2 rounded-md text-xs cursor-pointer flex items-center justify-between transition-colors ${
                    targetMoveFolder === '' ? 'bg-indigo-50 text-indigo-700 font-bold border border-indigo-200' : 'hover:bg-white text-gray-700'
                  }`}
                >
                  <span className="flex items-center gap-1.5">📁 / 项目根目录</span>
                  {targetMoveFolder === '' && <span className="text-[10px] text-indigo-500">当前选定</span>}
                </div>
                {directories.map(d => (
                  <div
                    key={d}
                    onClick={() => setTargetMoveFolder(d)}
                    className={`px-3 py-2 rounded-md text-xs cursor-pointer flex items-center justify-between transition-colors ${
                      targetMoveFolder === d ? 'bg-indigo-50 text-indigo-700 font-bold border border-indigo-200' : 'hover:bg-white text-gray-700'
                    }`}
                  >
                    <span className="flex items-center gap-1.5">📂 {d}</span>
                    {targetMoveFolder === d && <span className="text-[10px] text-indigo-500">当前选定</span>}
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setShowMoveModal(false)}
                className="px-3 py-1.5 text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-100 rounded"
              >
                取消
              </button>
              <button
                onClick={handleBatchMoveFiles}
                disabled={isMovingFiles}
                className="px-3.5 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded flex items-center gap-1 transition disabled:opacity-50"
              >
                {isMovingFiles && <Loader2 className="w-3 h-3 animate-spin" />}
                确认移动
              </button>
            </div>
          </div>
        </div>
      )}
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
