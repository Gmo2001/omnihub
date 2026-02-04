import React, { useState, useEffect } from 'react';
import { BackendAPI } from '../services/dataService';
import { User, Role } from '../types';
import { useOmniHub } from '../context/OmniHubContext';
import { X, Save, Search, UserCog, Activity, Briefcase, Folder } from 'lucide-react';
import SystemStatus from './Admin/SystemStatus';
import SyncManager from './Admin/SyncManager';

const AdminUserManagement = ({ onClose }: { onClose: () => void }) => {
    const { token } = useOmniHub();
    const [activeTab, setActiveTab] = useState<'users' | 'system' | 'sync'>('users');
    const [users, setUsers] = useState<User[]>([]);
    const [loading, setLoading] = useState(false);
    const [search, setSearch] = useState("");
    const [editingUser, setEditingUser] = useState<string | null>(null);
    const [editForm, setEditForm] = useState<Partial<User>>({});

    useEffect(() => {
        if (activeTab === 'users') {
            loadUsers();
        }
    }, [activeTab]);

    const loadUsers = async () => {
        setLoading(true);
        try {
            const list = await BackendAPI.getUsers(token);
            setUsers(list);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async (email: string) => {
        try {
            await BackendAPI.updateUser(email, editForm, token);
            setEditingUser(null);
            loadUsers();
        } catch (e) {
            alert("Update Failed");
        }
    };

    const filteredUsers = users.filter(u =>
        u.email.toLowerCase().includes(search.toLowerCase()) ||
        u.displayName?.toLowerCase().includes(search.toLowerCase())
    );

    return (
        <div className="absolute inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-8 animate-in fade-in duration-200">
            <div className="bg-[#1E1F2E] border border-white/10 w-full max-w-4xl h-[80vh] rounded-2xl shadow-2xl flex flex-col overflow-hidden">
                {/* Header */}
                <div className="p-6 border-b border-white/10 flex justify-between items-center bg-[#181926]">
                    <div className="flex items-center gap-4">
                        <div className="p-3 bg-indigo-500/20 rounded-xl">
                            <UserCog size={24} className="text-indigo-400" />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-white">Admin Console</h2>
                            <p className="text-sm text-slate-400">Manage users and system health</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-white/5 rounded-lg text-slate-400 hover:text-white transition-colors">
                        <X size={20} />
                    </button>
                </div>

                {/* Tabs */}
                <div className="flex px-6 border-b border-white/5 bg-[#13141F]">
                    <button
                        onClick={() => setActiveTab('users')}
                        className={`px-4 py-3 text-sm font-bold border-b-2 transition-colors flex items-center gap-2 ${activeTab === 'users' ? 'border-indigo-500 text-white' : 'border-transparent text-slate-500 hover:text-slate-300'}`}
                    >
                        <UserCog size={16} />
                        User Management
                    </button>
                    <button
                        onClick={() => setActiveTab('system')}
                        className={`px-4 py-3 text-sm font-bold border-b-2 transition-colors flex items-center gap-2 ${activeTab === 'system' ? 'border-emerald-500 text-white' : 'border-transparent text-slate-500 hover:text-slate-300'}`}
                    >
                        <Activity size={16} />
                        System Health
                    </button>
                    <button
                        onClick={() => setActiveTab('sync')}
                        className={`px-4 py-3 text-sm font-bold border-b-2 transition-colors flex items-center gap-2 ${activeTab === 'sync' ? 'border-blue-500 text-white' : 'border-transparent text-slate-500 hover:text-slate-300'}`}
                    >
                        <Folder size={16} />
                        Sync Manager
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-hidden p-6 bg-[#09090b]">
                    {activeTab === 'system' && (
                        <div className="max-w-2xl mx-auto h-full overflow-y-auto">
                            <SystemStatus />
                        </div>
                    )}
                    {activeTab === 'sync' && (
                        <div className="max-w-3xl mx-auto h-full overflow-y-auto">
                            <SyncManager />
                        </div>
                    )}
                    {activeTab === 'users' && (
                        <div className="h-full flex flex-col space-y-4">
                            {/* Search */}
                            <div className="relative">
                                <Search size={16} className="absolute left-3 top-3 text-slate-500" />
                                <input
                                    type="text"
                                    placeholder="Search users..."
                                    className="w-full bg-[#1E1F2E] border border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500/50"
                                    value={search}
                                    onChange={e => setSearch(e.target.value)}
                                />
                            </div>

                            {/* Table */}
                            <div className="flex-1 overflow-y-auto border border-white/5 rounded-xl bg-[#1E1F2E]">
                                <table className="w-full text-left text-sm text-slate-400">
                                    <thead className="bg-white/5 text-slate-200 font-bold sticky top-0 backdrop-blur-md">
                                        <tr>
                                            <th className="p-4">User</th>
                                            <th className="p-4">Department</th>
                                            <th className="p-4">Role</th>
                                            <th className="p-4 text-right">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-white/5">
                                        {filteredUsers.map(user => (
                                            <tr key={user.email} className="hover:bg-white/5 transition-colors">
                                                <td className="p-4">
                                                    <div className="flex items-center gap-3">
                                                        <div className="w-8 h-8 rounded-full bg-indigo-500/20 flex items-center justify-center text-xs font-bold text-indigo-300">
                                                            {user.displayName?.[0] || user.email[0]}
                                                        </div>
                                                        <div>
                                                            <div className="font-bold text-slate-200">{user.displayName}</div>
                                                            <div className="text-xs text-slate-500">{user.email}</div>
                                                        </div>
                                                    </div>
                                                </td>
                                                {editingUser === user.email ? (
                                                    <select
                                                        className="bg-black/20 border border-white/10 rounded px-2 py-1 text-slate-200 w-full"
                                                        value={editForm.department_id || "UNKNOWN"}
                                                        onChange={e => {
                                                            const selectedId = e.target.value;
                                                            // Map ID to Name
                                                            const deptMap: Record<string, string> = {
                                                                "DEPT_MGT": "경영지원본부",
                                                                "DEPT_CORP_TAX": "법인세무본부",
                                                                "DEPT_PROP_TAX": "재산세무본부",
                                                                "DEPT_AUDIT": "회계감사본부",
                                                                "DEPT_CONSULT": "컨설팅본부",
                                                                "UNKNOWN": "미지정"
                                                            };
                                                            setEditForm({
                                                                ...editForm,
                                                                department_id: selectedId,
                                                                department: deptMap[selectedId] || selectedId
                                                            });
                                                        }}
                                                    >
                                                        <option value="UNKNOWN">미지정</option>
                                                        <option value="DEPT_MGT">경영지원본부</option>
                                                        <option value="DEPT_CORP_TAX">법인세무본부</option>
                                                        <option value="DEPT_PROP_TAX">재산세무본부</option>
                                                        <option value="DEPT_AUDIT">회계감사본부</option>
                                                        <option value="DEPT_CONSULT">컨설팅본부</option>
                                                    </select>
                                                ) : (
                                                    <div className="flex flex-col">
                                                        <span className="text-xs font-bold text-slate-300">{user.department || "-"}</span>
                                                        <span className="text-[10px] text-slate-500 font-mono">{user.department_id || "UNKNOWN"}</span>
                                                    </div>
                                                )}
                                                <td className="p-4">
                                                    {editingUser === user.email ? (
                                                        <select
                                                            className="bg-black/20 border border-white/10 rounded px-2 py-1 text-slate-200"
                                                            defaultValue={user.role}
                                                            onChange={e => setEditForm({ ...editForm, role: e.target.value as Role })}
                                                        >
                                                            <option value="user">User</option>
                                                            <option value="manager">Manager</option>
                                                            <option value="admin">Admin</option>
                                                        </select>
                                                    ) : (
                                                        <span className={`px-2 py-1 rounded text-xs font-bold ${user.role === 'admin' ? 'bg-indigo-500/20 text-indigo-300' : 'bg-slate-700/50'}`}>
                                                            {user.role}
                                                        </span>
                                                    )}
                                                </td>
                                                <td className="p-4 text-right">
                                                    {editingUser === user.email ? (
                                                        <div className="flex justify-end gap-2">
                                                            <button
                                                                onClick={() => handleSave(user.email)}
                                                                className="p-1.5 bg-emerald-500/20 text-emerald-400 rounded hover:bg-emerald-500/30"
                                                            >
                                                                <Save size={16} />
                                                            </button>
                                                            <button
                                                                onClick={() => setEditingUser(null)}
                                                                className="p-1.5 bg-red-500/20 text-red-400 rounded hover:bg-red-500/30"
                                                            >
                                                                <X size={16} />
                                                            </button>
                                                        </div>
                                                    ) : (
                                                        <button
                                                            onClick={() => {
                                                                setEditingUser(user.email);
                                                                setEditForm({});
                                                            }}
                                                            className="px-3 py-1.5 hover:bg-white/10 rounded text-slate-300 transition-colors text-xs"
                                                        >
                                                            Edit
                                                        </button>
                                                    )}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default AdminUserManagement;
