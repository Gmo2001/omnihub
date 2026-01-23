import React, { useEffect, useRef, useState, useMemo, memo } from 'react';
import * as d3 from 'd3';
import { groupDocsByVersion, getVersionRangeText, extractVersionMeta } from '../services/dataService';
import { ConceptNode, DocRecord, Role } from '../types';
import { useOmniHub } from '../context/OmniHubContext';
import { Network, ZoomIn, SearchCheck, LayoutTemplate, BrainCircuit, Layers } from 'lucide-react';
import { VirtualFilterState } from './OmniHubTab';

interface GraphVisualizerProps {
  viewModeState?: 'default' | 'local' | 'evidence';
  evidenceData?: { docs: DocRecord[], concepts: ConceptNode[] } | null;
  virtualFilters?: VirtualFilterState;
}

interface GraphNode extends d3.SimulationNodeDatum {
  id: string;
  label: string;
  type: 'concept' | 'doc' | 'folder' | 'virtualPath' | 'group';
  group?: string;
  data?: any; 
  x?: number;
  y?: number;
}

interface GraphLink extends d3.SimulationLinkDatum<GraphNode> {
  source: string | GraphNode;
  target: string | GraphNode;
  type?: 'related' | 'evidence' | 'contains' | 'root' | 'version';
}

// --- MEMOIZED GRAPH CANVAS ---
const GraphCanvas = memo(({
    docs,
    concepts,
    currentRole,
    addLog,
    selectedDoc,
    setSelectedDoc,
    activeCenterId,
    setActiveCenterId,
    viewModeState,
    evidenceData,
    virtualFilters
}: {
    docs: DocRecord[];
    concepts: ConceptNode[];
    currentRole: Role;
    addLog: (msg: string, level?: any, category?: any) => void;
    selectedDoc: DocRecord | null;
    setSelectedDoc: (doc: DocRecord | null) => void;
    activeCenterId: string | null;
    setActiveCenterId: (id: string | null) => void;
    viewModeState: 'default' | 'local' | 'evidence';
    evidenceData: any;
    virtualFilters: any;
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [stats, setStats] = useState({ nodes: 0, links: 0 });
  const [groupByFilename, setGroupByFilename] = useState(true);
  const [expandedGroups, setExpandedGroups] = useState<string[]>([]);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  const effectiveMode = viewModeState === 'evidence' ? 'evidence' : (activeCenterId ? 'local' : 'default');

  // Resize Observer
  useEffect(() => {
    if (!containerRef.current) return;
    const resizeObserver = new ResizeObserver((entries) => {
        if (!Array.isArray(entries) || !entries.length) return;
        const { width, height } = entries[0].contentRect;
        setDimensions({ width, height });
    });
    resizeObserver.observe(containerRef.current);
    return () => resizeObserver.disconnect();
  }, []);

  // 1. Generate Raw Nodes/Links based on current ViewMode/Filters
  const { rawNodes, rawLinks } = useMemo(() => {
    let nodes: GraphNode[] = [];
    let links: GraphLink[] = [];

    const filterDocs = (docsToFilter: DocRecord[]) => {
        return docsToFilter.filter(d => {
            if (currentRole === 'manager' && d.security === 'high') return false;
            if (currentRole === 'viewer' && d.security !== 'low') return false;
            if (virtualFilters) {
                if (virtualFilters.security.length > 0 && !virtualFilters.security.includes(d.security)) return false;
                if (virtualFilters.status.length > 0 && !virtualFilters.status.includes(d.status)) return false;
                if (virtualFilters.years.length > 0 && !virtualFilters.years.some(y => d.period.includes(y) || d.name.includes(y))) return false;
                if (virtualFilters.tags.length > 0 && !virtualFilters.tags.some(t => d.tags.includes(t))) return false;
            }
            return true;
        });
    };

    if (effectiveMode === 'default') {
        const topConcepts = [...concepts].sort((a, b) => b.createdAt - a.createdAt).slice(0, 50);
        nodes = topConcepts.map(c => ({ id: c.id, label: c.label, type: 'concept', data: c }));
        nodes.forEach((node, i) => {
            const numLinks = Math.random() > 0.7 ? 2 : 1;
            for (let j = 0; j < numLinks; j++) {
                const targetIndex = Math.floor(Math.random() * nodes.length);
                if (targetIndex !== i) {
                    links.push({ source: node.id, target: nodes[targetIndex].id, type: 'related' });
                }
            }
        });
    } 
    else if (effectiveMode === 'evidence' && evidenceData) {
        evidenceData.concepts.forEach((c: ConceptNode) => nodes.push({ id: c.id, label: c.label, type: 'concept', data: c }));
        const filteredEvidence = filterDocs(evidenceData.docs);
        filteredEvidence.forEach(d => {
            nodes.push({ id: d.id, label: d.name, type: 'doc', data: d });
            d.conceptIds.forEach(cId => {
                if (nodes.find(n => n.id === cId)) links.push({ source: cId, target: d.id, type: 'evidence' });
            });
        });
    } 
    else if (effectiveMode === 'local' && activeCenterId) {
        if (activeCenterId.startsWith('vpath-')) {
            const pathString = activeCenterId.replace('vpath-', '');
            const displayLabel = pathString.split('/').pop() || pathString;
            nodes.push({ id: activeCenterId, label: displayLabel, type: 'virtualPath' });
            const pathDocs = docs.filter(d => d.folderPath.includes(pathString));
            const filteredDocs = filterDocs(pathDocs).slice(0, 30);
            filteredDocs.forEach(d => {
                nodes.push({ id: d.id, label: d.name, type: 'doc', data: d });
                links.push({ source: activeCenterId, target: d.id, type: 'contains' });
            });
            const relatedConceptIds = new Set<string>();
            filteredDocs.forEach(d => d.conceptIds.forEach(cid => relatedConceptIds.add(cid)));
            const relatedConcepts = concepts.filter(c => relatedConceptIds.has(c.id)).slice(0, 8);
            relatedConcepts.forEach(c => {
                nodes.push({ id: c.id, label: c.label, type: 'concept', data: c });
                filteredDocs.filter(d => d.conceptIds.includes(c.id)).forEach(d => {
                        links.push({ source: c.id, target: d.id, type: 'evidence' });
                });
            });
        } else {
            const centerConcept = concepts.find(c => c.id === activeCenterId);
            const centerDoc = docs.find(d => d.id === activeCenterId);
            if (centerConcept) {
                nodes.push({ id: centerConcept.id, label: centerConcept.label, type: 'concept', data: centerConcept });
                const potentialNeighbors = concepts.filter(c => c.id !== centerConcept.id);
                const neighbors = [];
                for(let i=0; i<5; i++) {
                    if (potentialNeighbors.length === 0) break;
                    const idx = Math.floor(Math.random() * potentialNeighbors.length);
                    neighbors.push(potentialNeighbors[idx]);
                    potentialNeighbors.splice(idx, 1);
                }
                neighbors.forEach(n => {
                    nodes.push({ id: n.id, label: n.label, type: 'concept', data: n });
                    links.push({ source: centerConcept.id, target: n.id, type: 'related' });
                });
                let relatedDocs = docs.filter(d => d.conceptIds.includes(centerConcept.id));
                relatedDocs = filterDocs(relatedDocs);
                const statusWeight = { pending: 3, approved: 2, idle: 1, rejected: 0 };
                relatedDocs.sort((a, b) => statusWeight[a.status] - statusWeight[b.status] || b.updatedAt - a.updatedAt);
                relatedDocs.slice(0, 30).forEach(d => {
                    nodes.push({ id: d.id, label: d.name, type: 'doc', data: d });
                    links.push({ source: centerConcept.id, target: d.id, type: 'evidence' });
                });
            } else if (centerDoc) {
                 nodes.push({ id: centerDoc.id, label: centerDoc.name, type: 'doc', data: centerDoc });
                 const relatedConcepts = concepts.filter(c => centerDoc.conceptIds.includes(c.id));
                 relatedConcepts.forEach(c => {
                     nodes.push({ id: c.id, label: c.label, type: 'concept', data: c });
                     links.push({ source: c.id, target: centerDoc.id, type: 'evidence' });
                 });
            }
        }
    }
    return { rawNodes: nodes, rawLinks: links };
  }, [currentRole, effectiveMode, activeCenterId, evidenceData, docs, concepts, virtualFilters]);

  // 2. Grouping
  const { nodes: groupedNodes, links: groupedLinks } = useMemo(() => {
      if (!groupByFilename) return { nodes: rawNodes, links: rawLinks };
      const docsList: DocRecord[] = [];
      const nonDocNodes: GraphNode[] = [];
      const docNodeMap: Record<string, GraphNode> = {};
      rawNodes.forEach(n => {
          if (n.type === 'doc') {
              docsList.push(n.data);
              docNodeMap[n.id] = n;
          } else {
              nonDocNodes.push(n);
          }
      });
      const { groups, singles } = groupDocsByVersion(docsList);
      const finalNodes = [...nonDocNodes];
      const docIdToActiveNodeId: Record<string, string> = {};
      singles.forEach(d => {
          finalNodes.push({ id: d.id, label: d.name, type: 'doc', data: d, x: docNodeMap[d.id]?.x, y: docNodeMap[d.id]?.y });
          docIdToActiveNodeId[d.id] = d.id;
      });
      Object.entries(groups).forEach(([groupKey, docList]) => {
          const groupId = `group:${groupKey}`;
          const isExpanded = expandedGroups.includes(groupKey);
          const representative = docList[0]; 
          const versionText = getVersionRangeText(docList);
          const hasSSOT = docList.some(d => d.ssotRating);
          const groupNode: GraphNode = {
              id: groupId,
              label: isExpanded && docList.length > 12 ? `📚 ${groupKey} (+${docList.length - 12})` : `📚 ${groupKey} (x${docList.length})`,
              type: 'group',
              data: { groupKey, count: docList.length, representative, versionRangeText: versionText, hasSSOT, isExpanded },
              x: docNodeMap[representative.id]?.x,
              y: docNodeMap[representative.id]?.y
          };
          finalNodes.push(groupNode);
          docList.forEach(d => docIdToActiveNodeId[d.id] = groupId);
          if (isExpanded) {
              const visibleChildren = docList.slice(0, 12);
              visibleChildren.forEach((d, i) => {
                  const meta = extractVersionMeta(d.name);
                  let label = meta.versionNumber ? `v${meta.versionNumber}` : (meta.versionStatus || 'v?');
                  if (meta.versionStatus === 'final') label += ' 🏅';
                  else if (meta.versionStatus === 'approved') label += ' ✅';
                  else if (meta.versionStatus === 'draft') label += ' 📝';
                  else if (meta.versionStatus === 'revised') label += ' 🛠️';
                  finalNodes.push({
                      id: d.id,
                      label: label,
                      type: 'doc',
                      data: { ...d, isVersionChild: true },
                      x: (groupNode.x || 0) + Math.cos(i) * 10,
                      y: (groupNode.y || 0) + Math.sin(i) * 10
                  });
                  docIdToActiveNodeId[d.id] = d.id;
              });
          }
      });
      const finalLinks: GraphLink[] = [];
      const linkDedup = new Set<string>();
      rawLinks.forEach(link => {
          const sourceId = typeof link.source === 'string' ? link.source : link.source.id;
          const targetId = typeof link.target === 'string' ? link.target : link.target.id;
          const newSource = docIdToActiveNodeId[sourceId] || sourceId;
          const newTarget = docIdToActiveNodeId[targetId] || targetId;
          if (newSource !== newTarget) {
              const linkKey = `${newSource}-${newTarget}-${link.type}`;
              if (!linkDedup.has(linkKey)) {
                  linkDedup.add(linkKey);
                  finalLinks.push({ ...link, source: newSource, target: newTarget });
              }
          }
      });
      Object.entries(groups).forEach(([groupKey, docList]) => {
          if (expandedGroups.includes(groupKey)) {
              const groupId = `group:${groupKey}`;
              const visibleChildren = docList.slice(0, 12);
              visibleChildren.forEach(d => {
                  finalLinks.push({ source: groupId, target: d.id, type: 'version' });
              });
          }
      });
      return { nodes: finalNodes, links: finalLinks };
  }, [rawNodes, rawLinks, groupByFilename, expandedGroups]);

  useEffect(() => {
      setStats({ nodes: groupedNodes.length, links: groupedLinks.length });
  }, [groupedNodes, groupedLinks]);

  // 3. D3 Rendering
  useEffect(() => {
    if (!containerRef.current || !svgRef.current || dimensions.width === 0) return;
    const { width, height } = dimensions;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove(); 
    const g = svg.append("g");
    const zoom = d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.1, 4]).on("zoom", (event) => g.attr("transform", event.transform));
    svg.call(zoom);
    svg.call(zoom.transform, d3.zoomIdentity.translate(width/2, height/2).scale(0.8));

    const simulation = d3.forceSimulation<GraphNode>(groupedNodes)
        .force("link", d3.forceLink<GraphNode, GraphLink>(groupedLinks).id(d => d.id).distance(d => {
            if (d.type === 'version') return 40;
            return effectiveMode === 'default' ? 120 : 90;
        }))
        .force("charge", d3.forceManyBody().strength(d => {
            if (d.type === 'doc' && d.data?.isVersionChild) return -100;
            return effectiveMode === 'default' ? -400 : -300;
        }))
        .force("x", d3.forceX(0).strength(0.04))
        .force("y", d3.forceY(0).strength(0.04))
        .force("collide", d3.forceCollide(d => {
            if (d.type === 'group') return 55; 
            if (d.type === 'concept') return 50; 
            if (d.data?.isVersionChild) return 25;
            return (d.type === 'folder' || d.type === 'virtualPath') ? 60 : 35;
        }))
        .force("center", d3.forceCenter(0, 0));

    // Styles & Rendering (abbreviated for memoization)
    const colors = {
        concept: '#4ade80', doc: '#60a5fa', folder: '#fbbf24', bridgeFolder: '#f59e0b',
        virtualPath: '#818cf8', group: '#a78bfa', pending: '#facc15', link: '#334155',
        evidenceLink: '#6366f1', rootLink: '#fbbf24', pathLink: '#818cf8', relatedLink: '#a8a29e', versionLink: '#c084fc'
    };

    const link = g.append("g").selectAll("line").data(groupedLinks).join("line")
        .attr("stroke", d => {
            if (d.type === 'version') return colors.versionLink;
            if (d.type === 'evidence') return colors.evidenceLink;
            if (d.type === 'root') return colors.rootLink;
            if (d.type === 'contains' && activeCenterId?.startsWith('vpath-')) return colors.pathLink;
            if (d.type === 'contains') return colors.rootLink;
            if (d.type === 'related') return colors.relatedLink;
            return colors.link;
        })
        .attr("stroke-opacity", d => d.type === 'version' ? 0.5 : (d.type === 'evidence' || d.type === 'related' ? 0.4 : 0.2))
        .attr("stroke-width", d => d.type === 'evidence' ? 1.5 : (d.type === 'root' ? 2 : 2))
        .attr("stroke-dasharray", d => d.type === 'evidence' || d.type === 'related' || d.type === 'version' ? "4,3" : "none");

    const node = g.append("g").selectAll("g").data(groupedNodes).join("g")
        .attr("cursor", "pointer")
        .on("click", (event, d) => {
            event.stopPropagation();
            if (d.type === 'group') {
                const groupKey = d.data.groupKey;
                setExpandedGroups(prev => {
                    const isActive = prev.includes(groupKey);
                    if (isActive) {
                        addLog(`Group collapsed: ${groupKey}`, 'INFO');
                        return prev.filter(k => k !== groupKey);
                    } else {
                        let next = [...prev];
                        if (next.length >= 3) {
                            const removed = next.shift();
                            addLog(`Max expanded groups reached -> auto-collapsed ${removed}`, 'INFO');
                        }
                        next.push(groupKey);
                        addLog(`Group expanded: ${groupKey}`, 'INFO');
                        return next;
                    }
                });
                return;
            }
            if (d.type === 'concept') {
                if (activeCenterId !== d.id && effectiveMode !== 'evidence') {
                    addLog(`개념 노드 선택됨 -> ${d.label}`, 'INFO');
                    setActiveCenterId(d.id);
                }
            } else if (d.type === 'doc') {
                if (setSelectedDoc) setSelectedDoc(d.data as DocRecord);
            }
        });

    node.append("circle")
        .attr("r", d => {
            if (d.type === 'group') return 32; 
            if (d.type === 'folder' || d.type === 'virtualPath') return 24; 
            if (d.type === 'concept') return (d.id === activeCenterId ? 20 : 12);
            if (d.type === 'doc' && d.data?.isVersionChild) return 14;
            return 9;
        })
        .attr("fill", "#0f172a") 
        .attr("stroke", d => {
            if (d.id === activeCenterId) return d.type === 'virtualPath' ? colors.virtualPath : "#fbbf24";
            if (d.type === 'group') return colors.group;
            if (d.type === 'folder') { if (d.data?.isBridge) return colors.bridgeFolder; return colors.folder; }
            if (d.type === 'virtualPath') return colors.virtualPath;
            if (d.type === 'doc' && (d.data as DocRecord)?.status === 'pending') return colors.pending;
            if (d.type === 'doc' && d.data?.isVersionChild) return colors.versionLink;
            return d.type === 'concept' ? colors.concept : colors.doc;
        })
        .attr("stroke-width", d => {
            if (d.data?.isBridge) return 4;
            if (d.type === 'group') return 3;
            if (d.type === 'doc' && d.data?.isVersionChild) return 1.5;
            return (d.type === 'folder' || d.type === 'virtualPath') ? 3 : 2;
        })
        .attr("stroke-dasharray", d => d.data?.isBridge ? "4,2" : "none");

    node.each(function(d) {
        const sel = d3.select(this);
        if (d.type === 'doc' && !d.data?.isVersionChild) {
             sel.append("text").text("📄").attr("x", -4.5).attr("y", 3.5).attr("font-size", "9px").style("pointer-events", "none");
        } else if (d.type === 'folder') {
             sel.append("text").text("📁").attr("x", -8).attr("y", 5).attr("font-size", "16px").style("pointer-events", "none");
        } else if (d.type === 'virtualPath') {
             sel.append("text").text("🧠").attr("x", -8).attr("y", 5).attr("font-size", "16px").style("pointer-events", "none");
        } else if (d.type === 'group') {
             const icon = d.data?.isExpanded ? "📂" : "📚";
             sel.append("text").text(icon).attr("x", -9).attr("y", 6).attr("font-size", "18px").style("pointer-events", "none");
        }
    });
    
    node.filter(d => d.data?.isBridge).append("text").text("BRIDGE").attr("x", 0).attr("y", -30).attr("text-anchor", "middle").attr("fill", "#fbbf24").attr("font-size", "8px").attr("font-weight", "bold").attr("letter-spacing", "1px").style("pointer-events", "none").style("text-shadow", "0 2px 4px rgba(0,0,0,0.8)");
    
    // SSOT Star logic update
    node.filter(d => (d.type === 'doc' && d.data?.ssotRating) || (d.type === 'group' && d.data?.hasSSOT))
        .append("text")
        .text("★") // Unicode Star
        .attr("x", d => d.type === 'doc' && d.data?.isVersionChild ? 8 : 5)
        .attr("y", d => d.type === 'doc' && d.data?.isVersionChild ? -8 : -5)
        .attr("fill", d => {
            if (d.type === 'doc' && d.data?.ssotRating === 'silver') return '#94A3B8'; // Slate-400
            return '#FBBF24'; // Amber-400 (Gold)
        })
        .attr("font-size", d => {
            if (d.type === 'doc' && d.data?.ssotRating === 'silver') return "12px"; // Slightly smaller
            return "14px";
        })
        .style("pointer-events", "none")
        .style("text-shadow", "0 1px 2px rgba(0,0,0,0.8)");

    const labelGroup = node.append("g").attr("transform", d => {
        if (d.type === 'folder' || d.type === 'virtualPath' || d.type === 'group') return "translate(0, 42)";
        if (d.data?.isVersionChild) return "translate(0, 24)"; 
        return "translate(16, 5)";
    });

    labelGroup.each(function(d) {
        const sel = d3.select(this);
        const isCentered = d.type === 'folder' || d.type === 'virtualPath' || d.type === 'group' || d.data?.isVersionChild;
        const textAnchor = isCentered ? "middle" : "start";
        let label = d.label;
        if (!isCentered && label.length > 20) label = label.substring(0, 18) + '...';
        sel.append("text").text(label).attr("text-anchor", textAnchor).attr("stroke", "#020617").attr("stroke-width", 3).attr("fill", "none").attr("font-size", d => d.type === 'concept' ? "11px" : "10px").attr("font-weight", "bold").style("pointer-events", "none");
        sel.append("text").text(label).attr("text-anchor", textAnchor).attr("fill", d => {
                if (d.data?.isBridge) return '#fcd34d';
                if (d.type === 'virtualPath') return '#a5b4fc';
                if (d.type === 'concept') return "#f8fafc";
                if (d.type === 'folder') return '#fcd34d';
                if (d.type === 'group') return '#c084fc'; 
                if (d.data?.isVersionChild) return '#e2e8f0';
                return "#cbd5e1";
            }).attr("font-size", d => d.type === 'concept' ? "11px" : "10px").attr("font-weight", "bold").style("pointer-events", "none");
        if (d.type === 'group' && d.data?.versionRangeText && !d.data?.isExpanded) {
             sel.append("text").text(d.data.versionRangeText).attr("y", 12).attr("text-anchor", "middle").attr("fill", "#a78bfa").attr("font-size", "9px").style("pointer-events", "none");
        }
    });

    const drag = d3.drag<SVGGElement, GraphNode>()
        .on("start", (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
            d3.select(event.sourceEvent.target).attr("cursor", "grabbing");
        })
        .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on("end", (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null; d.fy = null;
            d3.select(event.sourceEvent.target).attr("cursor", "pointer");
        });
    node.call(drag);

    simulation.on("tick", () => {
        link.attr("x1", d => (d.source as GraphNode).x!).attr("y1", d => (d.source as GraphNode).y!).attr("x2", d => (d.target as GraphNode).x!).attr("y2", d => (d.target as GraphNode).y!);
        node.attr("transform", d => `translate(${d.x},${d.y})`);
    });

    return () => { simulation.stop(); };
  }, [groupedNodes, groupedLinks, currentRole, effectiveMode, activeCenterId, addLog, setSelectedDoc, dimensions]);

  const toggleGroupByFilename = () => {
      setGroupByFilename(prev => {
          const next = !prev;
          addLog(`Visual Clustering: ${next ? 'Enabled (Filename)' : 'Disabled'}`, 'INFO');
          if (!next) setExpandedGroups([]);
          return next;
      });
  };

  return (
    <div className="w-full h-full relative bg-[#050508]" ref={containerRef} onClick={() => {
            if (activeCenterId) {
                setActiveCenterId(null);
                addLog("뷰 초기화", 'INFO');
            }
        }}>
        <div className="absolute inset-0 opacity-20 pointer-events-none" style={{ backgroundImage: `radial-gradient(circle at center, #1e293b 1px, transparent 1px), linear-gradient(to right, #1e293b 1px, transparent 1px), linear-gradient(to bottom, #1e293b 1px, transparent 1px)`, backgroundSize: '24px 24px, 48px 48px, 48px 48px' }}></div>
        <div className="absolute top-6 left-6 z-10 flex flex-col gap-2 pointer-events-none">
            <div className={`px-4 py-2.5 rounded-xl border flex items-center gap-3 shadow-xl backdrop-blur-md bg-indigo-950/80 border-indigo-500/50`}>
                <LayoutTemplate className="text-indigo-400" size={18} />
                <div>
                    <div className="text-[10px] font-bold uppercase tracking-widest text-indigo-300">Current View</div>
                    <div className="text-sm font-bold text-white leading-none mt-0.5">Virtual (AI Path)</div>
                </div>
            </div>
            <div className="bg-[#1E1F2E]/80 backdrop-blur border border-white/10 px-4 py-2 rounded-xl text-xs text-slate-400 flex items-center gap-3 shadow-lg">
                <Network size={14} className="text-indigo-400"/>
                <span className="font-mono text-white font-bold">{stats.nodes}</span> Nodes
                <span className="w-px h-3 bg-white/10 mx-1"></span>
                <span className="font-mono text-white font-bold">{stats.links}</span> Edges
            </div>
            {effectiveMode === 'evidence' ? (
                <div className="bg-indigo-500/10 border border-indigo-500/50 px-4 py-2 rounded-xl text-[10px] text-indigo-200 flex items-center gap-2 animate-pulse font-bold uppercase tracking-wider">
                   <SearchCheck size={12} /> Search Mode
                </div>
            ) : effectiveMode === 'local' ? (
                <div className={`px-4 py-2 rounded-xl text-[10px] flex items-center gap-2 font-bold uppercase tracking-wider ${activeCenterId?.startsWith('vpath-') ? 'bg-indigo-500/10 border border-indigo-500/50 text-indigo-200' : 'bg-emerald-500/10 border border-emerald-500/50 text-emerald-200'}`}>
                   {activeCenterId?.startsWith('vpath-') ? <BrainCircuit size={12}/> : <ZoomIn size={12} />} 
                   {activeCenterId?.startsWith('vpath-') ? 'Virtual Path View' : 'Concept View'}
                </div>
            ) : null}
            <div className="pointer-events-auto">
                 <button onClick={toggleGroupByFilename} className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-all shadow-lg text-xs font-bold ${groupByFilename ? 'bg-violet-600 text-white border-violet-500 shadow-violet-500/30' : 'bg-[#1E1F2E]/80 text-slate-400 border-white/10 hover:bg-white/10'}`}>
                    <Layers size={14} /> Group by Version
                 </button>
            </div>
        </div>
        <svg ref={svgRef} className="w-full h-full block" />
    </div>
  );
});

// --- WRAPPER COMPONENT ---
const GraphVisualizer: React.FC<GraphVisualizerProps> = (props) => {
  const { 
      currentRole, addLog, docs, concepts,
      selectedDoc, setSelectedDoc, activeCenterId, setActiveCenterId 
  } = useOmniHub();

  return (
      <GraphCanvas 
          {...props}
          docs={docs}
          concepts={concepts}
          currentRole={currentRole}
          addLog={addLog}
          selectedDoc={selectedDoc}
          setSelectedDoc={setSelectedDoc}
          activeCenterId={activeCenterId}
          setActiveCenterId={setActiveCenterId}
      />
  );
};

export default GraphVisualizer;