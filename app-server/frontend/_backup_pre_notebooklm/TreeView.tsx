import { useEffect, useState, useRef, useMemo } from 'react';
import { useProjectStore } from '../../store/projectStore';
import { useAuthStore } from '../../store/authStore';
import { FileText, Loader2, CheckSquare, Square, Folder, FolderOpen, Trash2, Download, X } from 'lucide-react';

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

export default function TreeView({ projectId, onFileClick, canWrite = true }: TreeViewProps) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  // WHY: 双 Tab——“本案文档”显示项目本身的文件，“公共文档”显示引用的公共文档。
  const [activeTab, setActiveTab] = useState<'local' | 'public'>('local');
  const [refFiles, setRefFiles] = useState<FileItem[]>([]);
  const [refLoading, setRefLoading] = useState(false);

  const { checkedFileIds, toggleFileCheck, setCheckedFiles, activePreviewFile, setActivePreviewFile, refreshCounter, checkedRefIds, setCheckedRefIds } = useProjectStore();
  const { getAuthHeaders } = useAuthStore();
  const seenFileIdsRef = useRef<Set<string>>(new Set());
  const seenRefIdsRef = useRef<Set<string>>(new Set());

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
    fetchFiles();
    const timer = setInterval(fetchFiles, 5000);
    return () => clearInterval(timer);
  }, [projectId]);

  // 加载引用的公共文档文件列表
  const fetchRefFiles = async () => {
    setRefLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/projects/${projectId}/ref-files`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        setRefFiles(data.files || []);
        // WHY: 用 seenRefIdsRef 追踪已知文件，只对首次出现的文件自动勾选，
        //       用户取消勾选的文件不会被重新选中。
        const newFiles = data.files || [];
        const currentRefIds = useProjectStore.getState().checkedRefIds;
        const newIds: string[] = [];
        for (const f of newFiles) {
          if (!seenRefIdsRef.current.has(f.id)) {
            seenRefIdsRef.current.add(f.id);
            newIds.push(f.id);
          }
        }
        if (newIds.length > 0) {
          setCheckedRefIds([...currentRefIds, ...newIds]);
        }
      }
    } catch (e) {
      console.error('获取公共文档引用失败', e);
    } finally {
      setRefLoading(false);
    }
  };

  // WHY: 组件加载 / projectId 变化 / 切换Tab / 上传弹窗关闭(refreshCounter) 时均刷新引用列表，
  //       确保 Tab 标题上的数量始终正确。
  useEffect(() => {
    fetchRefFiles();
  }, [projectId, activeTab, refreshCounter]);

  // 删除文件：磁盘 + 向量库同步清理（区分本地文件和网络来源）
  const handleDeleteFile = async (file: FileItem, e: React.MouseEvent) => {
    e.stopPropagation();
    const isWebSource = file.source_type === 'web' || file.source_type === 'text';
    const label = isWebSource ? '网络资料' : '文件';

    if (!window.confirm(`确定要删除${label}「${file.filename}」吗？\n\n此操作将同时清除该${label}在知识库中的向量索引，不可恢复。`)) {
      return;
    }

    setDeletingId(file.id);
    try {
      let res: Response;
      if (isWebSource) {
        // WHY: 网络来源调用专用删除 API
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

      // 即时从前端状态中移除
      setFiles(prev => prev.filter(f => f.id !== file.id));
      setCheckedFiles(checkedFileIds.filter(id => id !== file.id));
      seenFileIdsRef.current.delete(file.id);

      // 如果正在预览该文件，关闭预览
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

  // 删除文件夹：递归清理磁盘 + 向量库
  const handleDeleteFolder = async (folderPath: string, folderName: string, fileCount: number, e: React.MouseEvent) => {
    e.stopPropagation();

    if (!window.confirm(`确定要删除文件夹「${folderName}」吗？\n\n该文件夹下共 ${fileCount} 个文件将被永久删除，\n同时清除所有关联的知识库向量索引。此操作不可恢复。`)) {
      return;
    }

    // 拼接完整的相对路径（projectId/folderPath）
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

      // 即时从前端状态中移除该文件夹下所有文件
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

  // 渲染后将新发现的文件夹自动加入展开集合
  useEffect(() => {
    const newFolders = new Set<string>();
    const collectFolders = (node: TreeNode, currentPath: string = '') => {
      Object.values(node.children).forEach(child => {
        if (child.isFolder) {
          const pathKey = currentPath ? `${currentPath}/${child.name}` : child.name;
          newFolders.add(pathKey);
          collectFolders(child, pathKey);
        }
      });
    };
    collectFolders(treeRoot);
    
    setExpandedFolders(prev => {
      let changed = false;
      const next = new Set(prev);
      newFolders.forEach(f => {
        if (!next.has(f)) {
          next.add(f);
          changed = true;
        }
      });
      return changed ? next : prev;
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

  const handleBulkDelete = async () => {
    if (checkedFileIds.length === 0) return;
    
    const filesToDelete = files.filter(f => checkedFileIds.includes(f.id));
    if (!window.confirm(`确定要批量删除已选中的 ${filesToDelete.length} 个文件吗？\n\n此操作将同时清除知识库中的向量索引，不可恢复。`)) {
      return;
    }

    setDeletingId('bulk-deleting');
    let successCount = 0;
    
    // 串行删除以保证稳定性，批量太大也可优化为 Promise.all 限流
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
                    onClick={(e) => handleDeleteFolder(pathKey, child.name, childIds.length, e)}
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
              {file.source_type === 'web' ? (
                <span className="w-4 h-4 mt-0.5 shrink-0 text-center leading-4" title={`网页来源: ${file.source_url || ''}`}>🌐</span>
              ) : file.source_type === 'text' ? (
                <span className="w-4 h-4 mt-0.5 shrink-0 text-center leading-4" title="粘贴文本">📋</span>
              ) : (
                <FileText className="w-4 h-4 mt-0.5 opacity-60 shrink-0 text-indigo-500" />
              )}
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
                  onClick={(e) => handleDeleteFile(file, e)}
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
      {/* Tab 切换条 */}
      <div className="flex border-b border-gray-200 mb-1">
        <button
          onClick={() => setActiveTab('local')}
          className={`flex-1 py-2 text-xs font-medium text-center transition-colors ${
            activeTab === 'local'
              ? 'text-blue-600 border-b-2 border-blue-600'
              : 'text-gray-400 hover:text-gray-600'
          }`}
        >
          本案文档 ({files.length})
        </button>
        <button
          onClick={() => setActiveTab('public')}
          className={`flex-1 py-2 text-xs font-medium text-center transition-colors ${
            activeTab === 'public'
              ? 'text-indigo-600 border-b-2 border-indigo-600'
              : 'text-gray-400 hover:text-gray-600'
          }`}
        >
          公共文档 ({refFiles.length})
        </button>
      </div>

      {activeTab === 'local' ? (
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
                   onClick={handleBulkDelete}
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
      ) : (
        /* 公共文档 Tab */
        <div className="flex flex-col gap-2">
          {refLoading ? (
            <div className="flex justify-center py-4">
              <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
            </div>
          ) : refFiles.length === 0 ? (
            <div className="text-gray-400 text-center mt-4 text-sm">
              暂无引用的公共文档
              <p className="text-xs text-gray-300 mt-1">在上传界面中点击"引用公共文档"添加</p>
            </div>
          ) : (
            <>
              {/* 公共文档工具栏 */}
              <div className="flex items-center justify-between pb-2 border-b border-gray-100 px-1 flex-nowrap gap-1">
                <div
                  className="flex items-center gap-1.5 cursor-pointer group shrink-0"
                  onClick={() => {
                    if (checkedRefIds.length === refFiles.length) {
                      setCheckedRefIds([]);
                    } else {
                      setCheckedRefIds(refFiles.map(f => f.id));
                    }
                  }}
                >
                  <div className={`mt-0.5 shrink-0 ${checkedRefIds.length > 0 ? 'text-indigo-500' : 'text-gray-300'}`}>
                    {checkedRefIds.length === refFiles.length ? <CheckSquare className="w-4 h-4 group-hover:opacity-80" /> : <Square className="w-4 h-4 group-hover:text-indigo-400" />}
                  </div>
                  <span className="text-sm font-medium text-gray-700 group-hover:text-indigo-600 transition-colors whitespace-nowrap">
                    全选({checkedRefIds.length}/{refFiles.length})
                  </span>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {checkedRefIds.length > 0 && (
                    <button
                      onClick={() => handleDownload(
                        refFiles.filter(f => checkedRefIds.includes(f.id)).map(f => f.path),
                        `公共文档_${checkedRefIds.length}个文件.zip`
                      )}
                      disabled={downloadingId === 'bulk-ref-downloading'}
                      className="text-xs text-blue-500 font-medium hover:bg-blue-50 px-2 py-1 rounded flex items-center gap-1 transition-colors"
                    >
                      <Download className="w-3 h-3" />
                      下载 ({checkedRefIds.length})
                    </button>
                  )}
                  {checkedRefIds.length > 0 && (
                    <button
                      onClick={async () => {
                        if (!window.confirm(`确定要取消引用这 ${checkedRefIds.length} 个公共文档吗？\n\n此操作仅移除引用关系，不会删除公共文档库中的原始文件。`)) return;
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
                      }}
                      className="text-xs text-orange-500 font-medium hover:bg-orange-50 px-2 py-1 rounded flex items-center gap-1 transition-colors"
                    >
                      <X className="w-3 h-3" />
                      排除 ({checkedRefIds.length})
                    </button>
                  )}
                </div>
              </div>

              {/* 公共文档文件列表 */}
              <div className="space-y-0.5 pb-4">
                {refFiles.map(file => {
                  const isChecked = checkedRefIds.includes(file.id);
                  return (
                    <div
                      key={file.id}
                      className={`flex items-start gap-1 p-1.5 rounded cursor-pointer transition-colors group/file ${
                        isChecked ? 'bg-indigo-50 text-indigo-700' : 'hover:bg-gray-50 text-gray-700'
                      }`}
                      style={{ paddingLeft: '6px' }}
                    >
                      <div
                        className="mt-0.5 text-indigo-500 shrink-0"
                        onClick={() => {
                          setCheckedRefIds(
                            checkedRefIds.includes(file.id)
                              ? checkedRefIds.filter(id => id !== file.id)
                              : [...checkedRefIds, file.id]
                          );
                        }}
                      >
                        {isChecked ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4 text-gray-300" />}
                      </div>
                      <div className="flex items-start gap-1.5 flex-1 min-w-0 ml-0.5"
                        onClick={() => onFileClick?.(file)}
                      >
                        <span className="w-4 h-4 mt-0.5 shrink-0 text-center leading-4" title="公共文档">📚</span>
                        <div className="flex-1 min-w-0">
                          <div className="truncate text-sm" title={file.filename}>
                            {file.filename}
                          </div>
                          <div className="text-[10px] text-gray-400">
                            {(file.size / 1024).toFixed(1)} KB · 公共文档
                          </div>
                        </div>
                      </div>

                      {/* 悬浮下载与排除按钮 */}
                      <div className="flex items-center gap-1 mt-0.5 opacity-0 group-hover/file:opacity-100 transition-opacity shrink-0">
                        <button
                          className="p-0.5 rounded hover:bg-blue-100 text-gray-300 hover:text-blue-500"
                          title={`下载 ${file.filename}`}
                          onClick={(e) => { e.stopPropagation(); handleDownload([file.path], file.filename); }}
                        >
                          <Download className="w-3.5 h-3.5" />
                        </button>
                        <button
                          className="p-0.5 rounded hover:bg-orange-100 text-gray-300 hover:text-orange-500"
                          title={`排除 ${file.filename}`}
                          onClick={async (e) => {
                            e.stopPropagation();
                            if (!window.confirm(`确定要取消引用「${file.filename}」吗？\n\n此操作仅移除引用关系，不会删除原始文件。`)) return;
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
                              }
                            } catch (err) {
                              console.error('排除失败', err);
                            }
                          }}
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
