/* global React, I, TreeNode, deptHelpers */
const { useState, useRef, useEffect, useMemo, useCallback } = window.React;

/* ===========================================================
   PeopleScreen — Personnes
   Two-pane layout: department tree (left) + people table (right).
   Drag & drop people across departments (with ghost + highlight).
   =========================================================== */

const PeopleScreen = () => {
  /* ---------------- state ---------------- */
  const [depts, setDepts] = useState(window.INITIAL_DEPTS);
  const [people, setPeople] = useState(window.INITIAL_PEOPLE);
  const [selected, setSelected] = useState('d-root');
  const [showSub, setShowSub] = useState(true);
  const [expanded, setExpanded] = useState(new Set(['d-root', 'd-prod']));
  const [deptSearch, setDeptSearch] = useState('');
  const [pplSearch, setPplSearch] = useState('');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filters, setFilters] = useState({ id: '', name: '', card: '', period: 'Toutes', state: 'Toutes', phone: '', email: '' });
  const [appliedFilters, setAppliedFilters] = useState(filters);
  const [selRows, setSelRows] = useState(new Set());
  const [sort, setSort] = useState({ col: 'id', dir: 'asc' });

  /* DnD state */
  const [draggingPerson, setDraggingPerson] = useState(null); // person id
  const [draggingDept, setDraggingDept] = useState(null);     // dept id
  const [dragOverDept, setDragOverDept] = useState(null);
  const [ghost, setGhost] = useState(null);                   // {x, y, label, sub, count}

  /* Popovers */
  const [contextMenu, setContextMenu] = useState(null);  // {deptId, x, y}
  const [colorPopover, setColorPopover] = useState(null); // {deptId, x, y}
  const [confirmDelete, setConfirmDelete] = useState(null); // deptId

  /* New department inline */
  const [newDept, setNewDept] = useState(null);  // {parent}
  const [renaming, setRenaming] = useState(null);

  /* Toasts */
  const [toasts, setToasts] = useState([]);
  const toastIdRef = useRef(1);
  const undoRef = useRef(null);

  const showToast = useCallback((msg, undoFn) => {
    const id = toastIdRef.current++;
    setToasts(ts => [...ts, { id, msg, hasUndo: !!undoFn }]);
    undoRef.current = undoFn;
    setTimeout(() => setToasts(ts => ts.filter(t => t.id !== id)), 5200);
  }, []);

  /* ---------------- derived ---------------- */
  const visibleDepts = useMemo(() => {
    if (!deptSearch.trim()) return null;
    const q = deptSearch.toLowerCase();
    const matches = new Set();
    Object.values(depts).forEach(d => { if (d.name.toLowerCase().includes(q)) matches.add(d.id); });
    // also include ancestors so the tree path is visible
    const result = new Set();
    matches.forEach(id => {
      let cur = id;
      while (cur) { result.add(cur); cur = depts[cur]?.parent; }
    });
    return result;
  }, [deptSearch, depts]);

  const filteredPeople = useMemo(() => {
    let list = people;
    // department scope
    if (selected !== 'd-root' || !showSub) {
      const ids = showSub
        ? new Set([selected, ...deptHelpers.findDescendants(selected, depts)])
        : new Set([selected]);
      // d-root with showSub on = everyone
      if (!(selected === 'd-root' && showSub)) {
        list = list.filter(p => ids.has(p.dept));
      }
    }
    // Search
    if (pplSearch.trim()) {
      const q = pplSearch.toLowerCase();
      list = list.filter(p => p.first.toLowerCase().includes(q) || p.last.toLowerCase().includes(q) || p.id.includes(q));
    }
    // Applied filters
    const f = appliedFilters;
    if (f.id) list = list.filter(p => p.id.includes(f.id));
    if (f.name) {
      const q = f.name.toLowerCase();
      list = list.filter(p => p.first.toLowerCase().includes(q) || p.last.toLowerCase().includes(q));
    }
    // sort
    const dir = sort.dir === 'asc' ? 1 : -1;
    list = [...list].sort((a, b) => {
      const av = a[sort.col] ?? '';
      const bv = b[sort.col] ?? '';
      if (sort.col === 'id') return (parseInt(av) - parseInt(bv)) * dir || String(av).localeCompare(String(bv)) * dir;
      return String(av).localeCompare(String(bv), 'fr') * dir;
    });
    return list;
  }, [people, selected, showSub, depts, pplSearch, appliedFilters, sort]);

  const activeFilterCount = useMemo(() => {
    return Object.entries(appliedFilters).filter(([k, v]) => v && v !== '' && v !== 'Toutes').length;
  }, [appliedFilters]);

  const allSelected = filteredPeople.length > 0 && filteredPeople.every(p => selRows.has(p.id));
  const someSelected = !allSelected && filteredPeople.some(p => selRows.has(p.id));

  /* ---------------- DnD handlers ---------------- */
  const handleDragStart = (personId, e) => {
    setDraggingPerson(personId);
    // Selection-aware: drag the whole selection if this row is selected
    const isInSel = selRows.has(personId);
    const movingIds = isInSel ? Array.from(selRows) : [personId];
    const main = people.find(p => p.id === personId);
    if (!main) return;
    e.dataTransfer.effectAllowed = 'move';
    // Hide the default ghost
    const blank = document.createElement('canvas');
    blank.width = blank.height = 1;
    e.dataTransfer.setDragImage(blank, 0, 0);
    e.dataTransfer.setData('text/plain', JSON.stringify({ kind: 'people', ids: movingIds }));
    setGhost({
      x: e.clientX, y: e.clientY,
      label: `${main.first} ${main.last}`.trim(),
      sub: `ID ${main.id}`,
      count: movingIds.length,
    });
  };

  const handleDragEnd = () => {
    setDraggingPerson(null);
    setDraggingDept(null);
    setDragOverDept(null);
    setGhost(null);
  };

  const handleDragStartDept = (deptId, e) => {
    if (deptId === 'd-root') { e.preventDefault(); return; }
    setDraggingDept(deptId);
    const d = depts[deptId];
    e.dataTransfer.effectAllowed = 'move';
    const blank = document.createElement('canvas');
    blank.width = blank.height = 1;
    e.dataTransfer.setDragImage(blank, 0, 0);
    e.dataTransfer.setData('text/plain', JSON.stringify({ kind: 'dept', id: deptId }));
    setGhost({ x: e.clientX, y: e.clientY, label: d.name, sub: 'Département', count: 0, isDept: true });
  };

  /* Track mouse for ghost while dragging */
  useEffect(() => {
    if (!ghost) return;
    const onMove = (e) => setGhost(g => g ? { ...g, x: e.clientX, y: e.clientY } : null);
    window.addEventListener('dragover', onMove);
    return () => window.removeEventListener('dragover', onMove);
  }, [ghost]);

  const onDragOverDept = (deptId) => {
    setDragOverDept(deptId);
  };

  const onDropDept = (targetId) => {
    // Person → department
    if (draggingPerson) {
      const isInSel = selRows.has(draggingPerson);
      const movingIds = isInSel ? Array.from(selRows) : [draggingPerson];
      const before = people.map(p => ({ ...p }));
      setPeople(prev => prev.map(p => movingIds.includes(p.id) ? { ...p, dept: targetId } : p));
      setSelRows(new Set());
      const target = depts[targetId];
      const main = people.find(p => p.id === draggingPerson);
      const label = movingIds.length > 1
        ? `${movingIds.length} personnes déplacées vers ${target.name}.`
        : `${main.first || 'Personne'} déplacé(e) vers ${target.name}.`;
      showToast(label, () => setPeople(before));
    }
    // Department → department (reparenting)
    if (draggingDept) {
      const moving = draggingDept;
      if (moving !== targetId && targetId !== moving) {
        const descendants = deptHelpers.findDescendants(moving, depts);
        if (!descendants.has(targetId)) {  // can't drop into own descendant
          const oldParent = depts[moving].parent;
          if (oldParent !== targetId) {
            setDepts(prev => {
              const next = { ...prev };
              // remove from old parent
              if (oldParent) next[oldParent] = { ...next[oldParent], children: next[oldParent].children.filter(c => c !== moving) };
              // add to new parent
              next[targetId] = { ...next[targetId], children: [...next[targetId].children, moving] };
              next[moving] = { ...next[moving], parent: targetId };
              return next;
            });
            setExpanded(new Set([...expanded, targetId]));
            showToast(`${depts[moving].name} déplacé vers ${depts[targetId].name}.`);
          }
        }
      }
    }
    handleDragEnd();
  };

  /* ---------------- Department CRUD ---------------- */
  const addDept = (parentId) => {
    setExpanded(new Set([...expanded, parentId]));
    setNewDept({ parent: parentId });
  };

  const commitNewDept = (name) => {
    if (!name.trim()) { setNewDept(null); return; }
    const id = 'd-' + Math.random().toString(36).slice(2, 8);
    const parent = newDept.parent;
    const colors = ['blue','orange','green','pink','violet','amber','teal','slate'];
    const usedColors = Object.values(depts).map(d => d.color);
    const color = colors.find(c => !usedColors.includes(c)) || 'slate';
    setDepts(prev => {
      const next = { ...prev };
      next[id] = { id, name: name.trim(), icon: 'folder', color, parent, children: [] };
      next[parent] = { ...next[parent], children: [...next[parent].children, id] };
      return next;
    });
    setNewDept(null);
  };

  const renameDept = (deptId, name) => {
    if (name.trim()) {
      setDepts(prev => ({ ...prev, [deptId]: { ...prev[deptId], name: name.trim() } }));
    }
    setRenaming(null);
  };

  const deleteDept = (deptId) => {
    if (deptId === 'd-root') return;
    const d = depts[deptId];
    const parentId = d.parent;
    // Move all people in this dept (and descendants) to parent
    const allIds = new Set([deptId, ...deptHelpers.findDescendants(deptId, depts)]);
    setPeople(prev => prev.map(p => allIds.has(p.dept) ? { ...p, dept: parentId } : p));
    setDepts(prev => {
      const next = { ...prev };
      // remove all descendants
      allIds.forEach(id => delete next[id]);
      next[parentId] = { ...next[parentId], children: next[parentId].children.filter(c => c !== deptId) };
      return next;
    });
    if (selected === deptId) setSelected(parentId);
    setConfirmDelete(null);
    showToast(`Département "${d.name}" supprimé. Personnes déplacées vers ${depts[parentId].name}.`);
  };

  const setDeptColor = (deptId, color) => {
    setDepts(prev => ({ ...prev, [deptId]: { ...prev[deptId], color } }));
  };
  const setDeptIcon = (deptId, icon) => {
    setDepts(prev => ({ ...prev, [deptId]: { ...prev[deptId], icon } }));
  };

  /* ---------------- Row selection ---------------- */
  const toggleRow = (id) => {
    const next = new Set(selRows);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelRows(next);
  };
  const toggleAll = () => {
    if (allSelected) setSelRows(new Set());
    else setSelRows(new Set(filteredPeople.map(p => p.id)));
  };

  const sortBy = (col) => {
    setSort(s => s.col === col ? { col, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { col, dir: 'asc' });
  };

  /* ---------------- Click outside popovers ---------------- */
  useEffect(() => {
    const onClick = (e) => {
      if (e.target.closest('.popover')) return;
      if (e.target.closest('.tn__menu')) return;
      setContextMenu(null);
      setColorPopover(null);
    };
    window.addEventListener('mousedown', onClick);
    return () => window.removeEventListener('mousedown', onClick);
  }, []);

  /* ---------------- Render ---------------- */
  const path = deptHelpers.deptPath(selected, depts);
  const selectedDept = depts[selected];
  const selectedColor = window.DEPT_COLORS[selectedDept?.color] || window.DEPT_COLORS.blue;

  return (
    <div>
      {/* Page header */}
      <div className="ph">
        <div>
          <h1 className="ph__title">Personnes</h1>
          <p className="ph__sub">
            {filteredPeople.length} personne{filteredPeople.length > 1 ? 's' : ''} dans <strong style={{color:'var(--fg1)'}}>{selectedDept?.name}</strong>
            {showSub && selectedDept?.children.length > 0 && <> · sous-départements inclus</>}
            {' '}· glissez une ligne sur un département pour la déplacer.
          </p>
        </div>
        <div className="ph__actions">
          <button className="btn btn--secondary"><I.upload size={15}/> Importer</button>
          <button className="btn btn--secondary"><I.download size={15}/> Exporter</button>
          <button className="btn btn--primary"><I.plus size={15}/> Ajouter une personne</button>
        </div>
      </div>

      <div className="pp">
        {/* ===== LEFT: Department tree ===== */}
        <aside className="dept">
          <div className="dept__hd">
            <div className="dept__title-row">
              <div className="dept__title">
                <I.building size={14}/> Départements
                <span className="pill">{Object.keys(depts).length}</span>
              </div>
              <button className="dept__addbtn" onClick={() => addDept('d-root')} title="Ajouter un département à la racine">
                <I.plus/>
              </button>
            </div>
            <div className="dept__search">
              <I.searchFull/>
              <input type="text" placeholder="Rechercher un département…" value={deptSearch} onChange={(e) => setDeptSearch(e.target.value)} />
            </div>
          </div>

          <div className="dept__tree">
            <TreeNode
              deptId="d-root"
              depts={depts} people={people} depth={0}
              expanded={expanded} setExpanded={setExpanded}
              selected={selected} onSelect={setSelected}
              showSub={showSub}
              dragOver={dragOverDept} onDragOverDept={onDragOverDept} onDropDept={onDropDept}
              onOpenMenu={(deptId, rect) => setContextMenu({ deptId, x: rect.right - 200, y: rect.bottom + 4 })}
              renaming={renaming}
              onStartRename={setRenaming}
              onCommitRename={renameDept}
              onCancelRename={() => setRenaming(null)}
              draggedDept={draggingDept}
              onDragStartDept={handleDragStartDept}
              onDragEndDept={handleDragEnd}
              newDeptParent={newDept?.parent}
              NewDeptInput={NewDeptInput}
              onCommitNewDept={commitNewDept}
              onCancelNewDept={() => setNewDept(null)}
            />
          </div>

          <div className="dept__ft">
            <button className="btn btn--secondary btn--sm" onClick={() => addDept('d-root')} style={{flex:1}}>
              <I.plus size={14}/> Ajouter un département
            </button>
          </div>
        </aside>

        {/* ===== RIGHT: People panel ===== */}
        <div>
          {/* Filters card */}
          <div className="filters">
            <div className="filters__hd" onClick={() => setFiltersOpen(!filtersOpen)}>
              <div className="filters__title">
                <I.filter/> Filtres avancés
                {activeFilterCount > 0 && <span className="filters__count">{activeFilterCount}</span>}
                {!filtersOpen && activeFilterCount === 0 && <span style={{color:'var(--fg3)', fontWeight:400}}>· ID, nom, n° de carte, période, état, téléphone, e-mail</span>}
              </div>
              <I.chevDown size={14} style={{ transform: filtersOpen ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform .2s', color: 'var(--fg3)' }}/>
            </div>
            {filtersOpen && (
              <div className="filters__bd">
                <div className="filters__field">
                  <label>ID</label>
                  <input type="text" placeholder="Veuillez le saisir…" value={filters.id} onChange={(e) => setFilters({ ...filters, id: e.target.value })}/>
                </div>
                <div className="filters__field">
                  <label>Nom</label>
                  <input type="text" placeholder="Veuillez le saisir…" value={filters.name} onChange={(e) => setFilters({ ...filters, name: e.target.value })}/>
                </div>
                <div className="filters__field">
                  <label>N° de carte</label>
                  <input type="text" placeholder="Veuillez saisir un numéro de carte." value={filters.card} onChange={(e) => setFilters({ ...filters, card: e.target.value })}/>
                </div>
                <div className="filters__field">
                  <label>Période d'effet</label>
                  <select value={filters.period} onChange={(e) => setFilters({ ...filters, period: e.target.value })}>
                    <option>Toutes</option><option>Cette semaine</option><option>Ce mois</option><option>Personnalisée…</option>
                  </select>
                </div>
                <div className="filters__field">
                  <label>État des identifiants</label>
                  <select value={filters.state} onChange={(e) => setFilters({ ...filters, state: e.target.value })}>
                    <option>Toutes</option><option>Enrôlés</option><option>En attente</option><option>Aucun identifiant</option>
                  </select>
                </div>
                <div className="filters__field">
                  <label>Numéro de téléphone</label>
                  <input type="text" placeholder="Veuillez le saisir…" value={filters.phone} onChange={(e) => setFilters({ ...filters, phone: e.target.value })}/>
                </div>
                <div className="filters__field" style={{ gridColumn: 'span 2' }}>
                  <label>E-mail</label>
                  <input type="text" placeholder="Veuillez le saisir…" value={filters.email} onChange={(e) => setFilters({ ...filters, email: e.target.value })}/>
                </div>
                <div className="filters__actions">
                  <button className="btn btn--ghost btn--sm" onClick={() => { setFilters({ id:'', name:'', card:'', period:'Toutes', state:'Toutes', phone:'', email:'' }); setAppliedFilters({ id:'', name:'', card:'', period:'Toutes', state:'Toutes', phone:'', email:'' }); }}>
                    Réinitialiser
                  </button>
                  <button className="btn btn--primary btn--sm" onClick={() => setAppliedFilters(filters)}>Filtrer</button>
                </div>
              </div>
            )}
          </div>

          {/* Toolbar */}
          <div className="toolbar">
            <div className="toolbar__left">
              <label className="iconbtn is-on" onClick={() => setShowSub(!showSub)} title="Afficher le sous-département" style={{ width: 'auto', padding: '0 10px', gap: 8, fontSize: 12.5 }}>
                <span style={{ width: 16, height: 16, borderRadius: 4, background: showSub ? 'var(--brand)' : 'var(--bg-surface)', border: showSub ? '0' : '1.5px solid var(--border-strong)', display:'grid', placeItems:'center' }}>
                  {showSub && <I.check size={11}/>}
                </span>
                <span style={{ color: 'var(--fg1)', fontWeight: 600 }}>Afficher le sous-département</span>
              </label>
              <div className="sep"/>
              <button className="iconbtn" onClick={() => addDept(selected === 'd-root' ? 'd-root' : selected)} title="Ajouter une personne / un sous-département"><I.plus/></button>
              <button className="iconbtn" disabled={selRows.size === 0} title="Supprimer la sélection"><I.trash/></button>
              <button className="iconbtn" title="Importer"><I.upload/></button>
              <button className="iconbtn" title="Exporter"><I.download/></button>
              <button className="iconbtn" title="Imprimer la liste"><I.copy/></button>
              <button className="iconbtn" title="Photos d'identité"><I.face/></button>
              <div className="toolbar__crumbs" style={{ marginLeft: 12 }}>
                {path.map((d, i) => (
                  <React.Fragment key={d.id}>
                    {i > 0 && <I.chevRight/>}
                    {i === path.length - 1 ? <strong>{d.name}</strong> : <span>{d.name}</span>}
                  </React.Fragment>
                ))}
              </div>
            </div>
            <div className="toolbar__right">
              <div className="toolbar-search">
                <I.searchFull/>
                <input type="text" placeholder="Rechercher prénom, nom, ID…" value={pplSearch} onChange={(e) => setPplSearch(e.target.value)}/>
              </div>
              <button className={`iconbtn${activeFilterCount > 0 ? ' is-on' : ''}`} onClick={() => setFiltersOpen(!filtersOpen)} title="Filtres">
                <I.filter/>
                {activeFilterCount > 0 && <span className="badge-dot"/>}
              </button>
              <button className="iconbtn" title="Colonnes"><I.cols/></button>
              <button className="iconbtn" title="Densité"><I.sliders/></button>
            </div>
          </div>

          {/* Table */}
          <div className="people-card">
            <div className="ptbl">
              <div className="ptbl__hd">
                <div onClick={toggleAll}>
                  <div className={`cb${allSelected ? ' is-on' : someSelected ? ' is-some' : ''}`}/>
                </div>
                <div></div>
                <div>Profil</div>
                <div className="sortable" onClick={() => sortBy('id')}>ID <I.arrowUpDown/></div>
                <div className="sortable" onClick={() => sortBy('first')}>Prénom <I.arrowUpDown/></div>
                <div className="sortable" onClick={() => sortBy('last')}>Nom de famille <I.arrowUpDown/></div>
                <div className="sortable" onClick={() => sortBy('dept')}>Service <I.arrowUpDown/></div>
                <div>Informations sur les identifiants</div>
              </div>

              {filteredPeople.length === 0 ? (
                <EmptyState/>
              ) : filteredPeople.map(p => {
                const d = depts[p.dept];
                const c = window.DEPT_COLORS[d?.color] || window.DEPT_COLORS.slate;
                const isSel = selRows.has(p.id);
                const isDragging = draggingPerson === p.id || (selRows.has(p.id) && draggingPerson && selRows.has(draggingPerson));
                const initials = (p.empty ? '?' : (p.first[0] || '') + (p.last[0] === '-' ? '' : (p.last[0] || ''))).toUpperCase();
                return (
                  <div
                    key={p.id}
                    className={`ptbl__row${isSel ? ' is-selected' : ''}${isDragging ? ' is-dragging' : ''}`}
                    draggable
                    onDragStart={(e) => handleDragStart(p.id, e)}
                    onDragEnd={handleDragEnd}
                  >
                    <div onClick={() => toggleRow(p.id)}>
                      <div className={`cb${isSel ? ' is-on' : ''}`}/>
                    </div>
                    <div className="grip" title="Glisser pour déplacer"><I.grip/></div>
                    <div className="avatar-ph">{initials || '·'}</div>
                    <div><a className="id-link" href="#">{p.id}</a></div>
                    <div className={`cell-name${p.first === 'No Name' ? ' is-empty' : ''}`}>{p.first}</div>
                    <div className={`cell-name${p.last === '--' ? ' is-empty' : ''}`}>{p.last}</div>
                    <div>
                      <span className="svc-chip" style={{ '--svc-bg': c.soft, '--svc-fg': c.fg, '--svc-bd': c.bd, '--svc-dot': c.dot }}>
                        <span className="swatch"/>
                        {d?.name || '—'}
                      </span>
                    </div>
                    <div className="idents">
                      <Ident on={!!p.ids.face}  color="#1F8A5B"><I.face/></Ident>
                      <Ident on={!!p.ids.card}  color="#2F6BE6"><I.card/></Ident>
                      <Ident on={!!p.ids.bt}    color="#7C3AED"><I.bluetooth/></Ident>
                      <Ident on={!!p.ids.fp}    color="#0EA5E9"><I.finger/></Ident>
                      <Ident on={!!p.ids.badge} color="#F59E0B"><I.badge/></Ident>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Pagination */}
          <div className="pgn">
            <div className="pgn__left">
              <span>Total : <strong>{filteredPeople.length}</strong></span>
              <select defaultValue="20"><option>10</option><option>20</option><option>50</option><option>100</option></select>
              <span>par page</span>
              {selRows.size > 0 && <span style={{color:'var(--brand)', fontWeight:600}}>· {selRows.size} sélectionnée{selRows.size>1?'s':''}</span>}
            </div>
            <div className="pgn__right">
              <button className="pg-btn" disabled><I.chevFirst/></button>
              <button className="pg-btn" disabled><I.chevLeft/></button>
              <button className="pg-btn" disabled><I.chevRight/></button>
              <button className="pg-btn" disabled><I.chevLast/></button>
              <input className="pg-num" defaultValue="1"/>
              <span>/ 1 page</span>
              <button className="btn btn--secondary btn--sm" style={{marginLeft:6}}>Accéder</button>
            </div>
          </div>
        </div>
      </div>

      {/* Drag ghost */}
      {ghost && (
        <div className="dragghost" style={{ left: ghost.x + 14, top: ghost.y + 14, transform: 'translate(0, 0)' }}>
          {!ghost.isDept && <div className="avatar-ph">{(ghost.label[0] || '·').toUpperCase()}</div>}
          {ghost.isDept && <div style={{ width: 28, height: 28, borderRadius: 6, background: 'var(--brand-soft)', color: 'var(--brand)', display:'grid', placeItems:'center' }}><I.folder/></div>}
          <div>
            <div className="nm">{ghost.label}</div>
            <div className="sub">{ghost.sub}{ghost.isDept ? '' : ' · vers un département'}</div>
          </div>
          {ghost.count > 1 && <span className="pill">+{ghost.count - 1}</span>}
        </div>
      )}

      {/* Context menu */}
      {contextMenu && (
        <ContextMenu
          x={contextMenu.x} y={contextMenu.y}
          deptId={contextMenu.deptId}
          depts={depts}
          onClose={() => setContextMenu(null)}
          onAddSub={(id) => { addDept(id); setContextMenu(null); }}
          onRename={(id) => { setRenaming(id); setContextMenu(null); }}
          onColor={(id, rect) => { setColorPopover({ deptId: id, x: contextMenu.x, y: contextMenu.y }); setContextMenu(null); }}
          onMoveUp={() => { setContextMenu(null); }}
          onDelete={(id) => { setConfirmDelete(id); setContextMenu(null); }}
        />
      )}

      {/* Color/icon popover */}
      {colorPopover && (
        <ColorIconPopover
          x={colorPopover.x} y={colorPopover.y}
          deptId={colorPopover.deptId}
          dept={depts[colorPopover.deptId]}
          onColor={(c) => setDeptColor(colorPopover.deptId, c)}
          onIcon={(i) => setDeptIcon(colorPopover.deptId, i)}
          onClose={() => setColorPopover(null)}
        />
      )}

      {/* Confirm delete */}
      {confirmDelete && (
        <div className="modal__veil" onClick={() => setConfirmDelete(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal__hd">
              <h3 className="modal__title">Supprimer "{depts[confirmDelete]?.name}" ?</h3>
              <p className="modal__sub">Les personnes du département seront déplacées vers <strong>{depts[depts[confirmDelete]?.parent]?.name}</strong>.</p>
            </div>
            <div className="modal__bd">
              {countPeopleIn(confirmDelete, depts, people, true) > 0 && (
                <p style={{display:'flex',gap:10,alignItems:'flex-start',padding:'10px 12px',background:'var(--warning-50)',border:'1px solid #FDE68A',borderRadius:8,color:'var(--warning-700)',margin:0}}>
                  <I.alert/>
                  <span><strong>{countPeopleIn(confirmDelete, depts, people, true)} personne(s)</strong> seront affectées.</span>
                </p>
              )}
            </div>
            <div className="modal__ft">
              <button className="btn btn--secondary" onClick={() => setConfirmDelete(null)}>Annuler</button>
              <button className="btn btn--danger" onClick={() => deleteDept(confirmDelete)}>Supprimer</button>
            </div>
          </div>
        </div>
      )}

      {/* Toasts */}
      {toasts.length > 0 && (
        <div className="toast-stack">
          {toasts.map(t => (
            <div key={t.id} className="toast">
              <div className="ic"><I.check size={12}/></div>
              <span>{t.msg}</span>
              {t.hasUndo && <button onClick={() => { if (undoRef.current) undoRef.current(); setToasts(ts => ts.filter(x => x.id !== t.id)); }}>Annuler</button>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

/* ============== sub components ============== */

const Ident = ({ on, color, children }) => (
  <div className={`ident${on ? ' is-on' : ''}`} style={{ '--ident-bg': color }}>
    {children}
  </div>
);

const NewDeptInput = ({ onCommit, onCancel, depth, parentName }) => {
  const ref = useRef(null);
  useEffect(() => { ref.current?.focus(); }, []);
  return (
    <div className="tn--new" style={{ marginLeft: depth * 14 }}>
      <I.plus size={12}/>
      <div className="tn__icon" style={{ background: 'var(--brand-soft)', color: 'var(--brand)' }}><I.folder size={12}/></div>
      <input
        ref={ref} className="tn__label-input"
        placeholder={parentName ? `Sous-département de ${parentName}…` : 'Nom du département…'}
        onBlur={(e) => onCommit(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') onCommit(e.target.value);
          if (e.key === 'Escape') onCancel();
        }}
      />
    </div>
  );
};

const ContextMenu = ({ x, y, deptId, depts, onClose, onAddSub, onRename, onColor, onDelete }) => {
  const isRoot = deptId === 'd-root';
  return (
    <div className="popover" style={{ left: x, top: y }}>
      <div className="item" onClick={() => onAddSub(deptId)}>
        <I.plus/> Ajouter un sous-département
      </div>
      <div className="sep"/>
      {!isRoot && <div className="item" onClick={() => onRename(deptId)}><I.pencil/> Renommer</div>}
      <div className="item" onClick={() => onColor(deptId)}><I.swatch/> Couleur & icône</div>
      {!isRoot && <>
        <div className="sep"/>
        <div className="item is-danger" onClick={() => onDelete(deptId)}><I.trash/> Supprimer</div>
      </>}
    </div>
  );
};

const ColorIconPopover = ({ x, y, deptId, dept, onColor, onIcon, onClose }) => (
  <div className="popover" style={{ left: x, top: y, minWidth: 220 }}>
    <div className="group-label">Couleur</div>
    <div className="swatches">
      {Object.entries(window.DEPT_COLORS).map(([key, c]) => (
        <button
          key={key}
          className={`swatch-btn${dept.color === key ? ' is-on' : ''}`}
          style={{ background: c.dot, borderColor: c.bd }}
          onClick={() => onColor(key)}
          title={c.label}
        />
      ))}
    </div>
    <div className="sep"/>
    <div className="group-label">Icône</div>
    <div className="icon-grid">
      {window.DEPT_ICONS.map(i => {
        const Ico = I[i] || I.folder;
        return (
          <button key={i} className={dept.icon === i ? 'is-on' : ''} onClick={() => onIcon(i)} title={i}>
            <Ico/>
          </button>
        );
      })}
    </div>
  </div>
);

const EmptyState = () => (
  <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--fg3)' }}>
    <div style={{ width: 48, height: 48, borderRadius: 12, background: 'var(--bg-subtle)', color: 'var(--fg4)', display: 'grid', placeItems: 'center', margin: '0 auto 12px' }}>
      <I.users size={22}/>
    </div>
    <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--fg1)', marginBottom: 4 }}>Aucune personne dans ce département</div>
    <div style={{ fontSize: 13, marginBottom: 16 }}>Ajoutez une personne ou glissez-en une depuis un autre département.</div>
    <button className="btn btn--primary btn--sm"><I.plus size={14}/> Ajouter une personne</button>
  </div>
);

const countPeopleIn = (deptId, depts, people, recursive) => window.deptHelpers.countPeopleIn(deptId, depts, people, recursive);

window.PeopleScreen = PeopleScreen;
