/* global React, I */
const { useState, useRef, useEffect, useMemo, useCallback } = window.React;

/* ------------- Department tree helpers ------------- */
const countPeopleIn = (deptId, depts, people, recursive = true) => {
  if (!recursive) return people.filter(p => p.dept === deptId).length;
  const ids = new Set([deptId]);
  const stack = [deptId];
  while (stack.length) {
    const cur = stack.pop();
    const d = depts[cur];
    if (!d) continue;
    d.children.forEach(c => { ids.add(c); stack.push(c); });
  }
  return people.filter(p => ids.has(p.dept)).length;
};

const findDescendants = (deptId, depts) => {
  const out = new Set();
  const walk = (id) => {
    const d = depts[id]; if (!d) return;
    d.children.forEach(c => { out.add(c); walk(c); });
  };
  walk(deptId);
  return out;
};

const deptPath = (deptId, depts) => {
  const path = [];
  let cur = deptId;
  while (cur && depts[cur]) { path.unshift(depts[cur]); cur = depts[cur].parent; }
  return path;
};

/* ------------- Tree node ------------- */
const TreeNode = ({
  deptId, depts, people, depth,
  expanded, setExpanded,
  selected, onSelect,
  showSub,
  dragOver, onDragOverDept, onDropDept,
  onOpenMenu,
  renaming, onStartRename, onCommitRename, onCancelRename,
  draggedDept, onDragStartDept, onDragEndDept,
  newDeptParent, NewDeptInput, onCommitNewDept, onCancelNewDept,
}) => {
  const d = depts[deptId];
  if (!d) return null;
  const c = window.DEPT_COLORS[d.color] || window.DEPT_COLORS.slate;
  const isOpen = expanded.has(deptId);
  const isLeaf = d.children.length === 0;
  const isActive = selected === deptId;
  const isDropping = dragOver === deptId;
  const count = countPeopleIn(deptId, depts, people, showSub);
  const isRenaming = renaming === deptId;
  const isDraggingSelf = draggedDept === deptId;

  const inputRef = useRef(null);
  useEffect(() => { if (isRenaming && inputRef.current) { inputRef.current.focus(); inputRef.current.select(); } }, [isRenaming]);

  const Icon = I[d.icon] || I.folder;

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    onDragOverDept(deptId);
  };
  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    onDropDept(deptId);
  };

  return (
    <>
      <div
        className={`tn${isActive ? ' is-active' : ''}${isDropping ? ' is-drop' : ''}${isDraggingSelf ? ' is-dragging-self' : ''}`}
        style={{
          paddingLeft: 8 + depth * 14,
          '--dept-icon-bg': c.soft,
          '--dept-icon-fg': c.fg,
        }}
        onClick={() => onSelect(deptId)}
        onDragOver={handleDragOver}
        onDragLeave={(e) => { e.stopPropagation(); }}
        onDrop={handleDrop}
        draggable={!isRenaming && deptId !== 'd-root'}
        onDragStart={(e) => onDragStartDept(deptId, e)}
        onDragEnd={onDragEndDept}
      >
        <div
          className={`tn__chev${isOpen ? ' is-open' : ''}${isLeaf ? ' is-leaf' : ''}`}
          onClick={(e) => { e.stopPropagation(); if (!isLeaf) setExpanded(new Set(isOpen ? [...expanded].filter(x => x !== deptId) : [...expanded, deptId])); }}
        >
          <I.chevRight/>
        </div>
        <div className="tn__icon"><Icon/></div>
        <div className="tn__label">
          {isRenaming
            ? <input
                ref={inputRef}
                className="tn__label-input"
                defaultValue={d.name}
                onBlur={(e) => onCommitRename(deptId, e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') { onCommitRename(deptId, e.target.value); }
                  if (e.key === 'Escape') { onCancelRename(); }
                }}
                onClick={(e) => e.stopPropagation()}
              />
            : d.name
          }
        </div>
        <div className="tn__count">{count}</div>
        <div
          className="tn__menu"
          onClick={(e) => { e.stopPropagation(); onOpenMenu(deptId, e.currentTarget.getBoundingClientRect()); }}
          aria-label="Menu"
        >
          <I.more/>
        </div>
      </div>
      {(isOpen || newDeptParent === deptId) && (!isLeaf || newDeptParent === deptId) && (
        <div className="tn__children">
          {d.children.map(cid => (
            <TreeNode
              key={cid}
              deptId={cid}
              depts={depts} people={people} depth={depth + 1}
              expanded={expanded} setExpanded={setExpanded}
              selected={selected} onSelect={onSelect}
              showSub={showSub}
              dragOver={dragOver} onDragOverDept={onDragOverDept} onDropDept={onDropDept}
              onOpenMenu={onOpenMenu}
              renaming={renaming} onStartRename={onStartRename} onCommitRename={onCommitRename} onCancelRename={onCancelRename}
              draggedDept={draggedDept} onDragStartDept={onDragStartDept} onDragEndDept={onDragEndDept}
              newDeptParent={newDeptParent} NewDeptInput={NewDeptInput} onCommitNewDept={onCommitNewDept} onCancelNewDept={onCancelNewDept}
            />
          ))}
          {newDeptParent === deptId && NewDeptInput && (
            <NewDeptInput onCommit={onCommitNewDept} onCancel={onCancelNewDept} depth={0} parentName={d.name}/>
          )}
        </div>
      )}
    </>
  );
};

window.TreeNode = TreeNode;
window.deptHelpers = { countPeopleIn, findDescendants, deptPath };
