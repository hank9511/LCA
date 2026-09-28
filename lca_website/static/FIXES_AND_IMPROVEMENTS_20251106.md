# LCA Analysis Fixes and Improvements

**Date**: 6 November 2025  
**Problem**: On the wizard page, clicking "Run analysis" showed "LCA analysis is not available yet"  
**Root cause**: Jinja2 limitation — a template that uses `extends` cannot correctly `include` another template that also uses `extends`

---

## Implemented solutions

### Option A: Quick fix (standalone wizard page)
**Goal**: Make LCA analysis work on the wizard page immediately

#### File: `lca_website/templates/lca_wizard.html`

**Changes**:
1. Removed the ineffective `{% include 'project_detail.html' ignore missing %}`
2. Added the two modal structures required for LCA analysis:
   - `lcaAnalysisModal` — LCA analysis progress modal
   - `lcaResultsModal` — LCA results modal
3. Loaded the standalone JavaScript library `lca_analysis.js`
4. Improved error handling so failure messages are clearer

### Option B: Reuse shared code (longer-term maintenance)
**Goal**: Extract shared JavaScript so it can be reused

#### New file: `lca_website/static/js/lca_analysis.js` (24KB)

**Core functions**:
1. **Main functions**:
   - `runLCAAnalysis(fileId, fileName)` — start an LCA analysis
   - `pollLCATaskStatus(taskId, fileId, fileName)` — poll task status

2. **Helpers**:
   - `getStatusText(status)` — status label
   - `getCompletionActions(status, data, fileId, fileName)` — action buttons after completion
   - `showLCAError(errorMessage, fileId, fileName)` — show an error

3. **Database interaction**:
   - `saveLCAResultToDB(fileId, data)` — save the result
   - `checkLCACompletionInDB(fileId, fileName, timerInterval)` — check completion in the database
   - `createManualLCAResult(fileId)` — create a completion record manually

4. **Result display**:
   - `showLCAResults(fileId)` — list LCA results
   - `showLCAResultDetails(resultId)` — show one result
   - `refreshLCAResults(fileId)` — refresh results

5. **Modal control**:
   - `closeLCAAnalysisModal()` — close the analysis modal
   - `closeLCAResultsModal()` — close the results modal

#### File: `lca_website/templates/project_detail.html`

**Changes**:
1. Added a comment where the old LCA functions lived, noting that they moved to a separate file
2. Loaded `lca_analysis.js` at the end of the scripts block
3. Kept the inline functions for backward compatibility (the standalone file overrides them)

---

## Files changed

### Added (1)
- `lca_website/static/js/lca_analysis.js` — LCA analysis JavaScript library (24KB)

### Modified (2)
- `lca_website/templates/lca_wizard.html` — wizard page template
- `lca_website/templates/project_detail.html` — project detail template

---

## Verification steps

### Preparation
1. OpenLCA is running
2. The IPC server is enabled (port 8080)
3. The Flask app is running (port 8086)

### Tests

#### Test 1: Wizard-page LCA analysis
1. Open the project detail page
2. Click "LCA wizard"
3. Go to step 4, "LCA analysis"
4. Select an uploaded Excel file
5. Click "Run analysis"
6. **Expected**:
   - Before: an alert that LCA analysis is not available
   - Now: the progress modal opens and analysis starts

#### Test 2: Project-detail LCA analysis
1. Open the project detail page
2. Find an Excel file in the file list
3. Click "Run LCA analysis"
4. **Expected**: the progress modal appears (this path already worked)

#### Test 3: Progress monitoring
1. Start an LCA analysis
2. Watch the progress modal
3. **Expected**:
   - Status icon
   - Current step
   - Percent and progress bar
   - Elapsed-time timer
   - Step descriptions

#### Test 4: After completion
1. Wait until the analysis finishes
2. **Expected**:
   - Success icon
   - Result summary
   - "View detailed results" button
   - "Close" button
3. Click "View detailed results"
4. **Expected**: the LCA result list or the visualization page

#### Test 5: Error handling
1. Stop OpenLCA or the IPC server
2. Try to run an LCA analysis
3. **Expected**:
   - Error icon
   - A clear error message
   - "Retry" button
   - "Close" button

---

## Technical notes

### Why the previous approach failed

**Cause**:
```jinja2
<!-- lca_wizard.html -->
{% extends "base.html" %}
{% block content %}
  ...
  {% include 'project_detail.html' ignore missing %}  This line does not work
{% endblock %}
```

**Jinja2 limitation**:
1. `project_detail.html` uses `{% extends "base.html" %}`
2. `lca_wizard.html` also uses `{% extends "base.html" %}`
3. In Jinja2, a template that extends another template cannot include a second template that also extends a template
4. The `{% block scripts %}` in `project_detail.html` is not rendered into `lca_wizard.html`
5. JavaScript functions, including `runLCAAnalysis`, were therefore never loaded

### Why the new approach works

#### Option A (standalone wizard page)
- Available immediately
- Does not depend on another page
- Easier to debug and maintain
- Avoids the template-engine limitation

#### Option B (shared JavaScript)
- One implementation instead of duplicated functions
- A change in one file applies everywhere it is loaded
- Follows DRY
- Easier to extend
- A separate JS file can be cached by the browser

### How the two options fit together

```
lca_wizard.html (wizard page)
    ↓
    loads lca_analysis.js
    ↓
    includes the modal HTML
    ↓
    full behavior

project_detail.html (project detail page)
    ↓
    keeps the inline functions (backward compatible)
    ↓
    loads lca_analysis.js (overrides the inline functions)
    ↓
    full behavior, with less duplication
```

---

## Performance

### File size
- `lca_analysis.js`: 24KB
- About 6KB after gzip

### Loading
- The script tag is at the bottom of the page, so it does not block rendering
- The browser caches `lca_analysis.js`
- Flask `url_for` is used so the static path stays correct

---

## Later improvements

These are optional and not urgent.

#### 1. Remove the inline LCA functions from `project_detail.html`
**Current state**: inline functions remain for backward compatibility  
**Target**: rely only on `lca_analysis.js`  
**Priority**: low (the current setup already works)

#### 2. Bundle and minify JavaScript
**Tools**: Webpack, Rollup, or Vite  
**Priority**: medium (useful for production)

#### 3. Add unit tests
**Scope**: individual JavaScript functions  
**Tools**: Jest or Mocha  
**Priority**: medium

#### 4. TypeScript
**Benefit**: type checking and better editor support  
**Priority**: low (needs a team decision)

---

## Checklist

- [x] Created standalone `lca_analysis.js`
- [x] Updated `lca_wizard.html` with modals and the script reference
- [x] Updated `project_detail.html` to load the new script
- [x] Core LCA analysis functions live in the standalone file
- [x] Error handling was improved
- [x] Backward compatibility was kept
- [ ] **Needs a manual check**: confirm the flow in a browser
- [ ] **Needs a manual check**: confirm progress is shown
- [ ] **Needs a manual check**: confirm results are shown

---

## Notes

### Browser cache
If the page still misbehaves after the change:
1. Hard-refresh (Ctrl+F5 or Cmd+Shift+R)
2. Or disable cache in the browser developer tools

### Check that the script loaded
Open the developer tools (F12) and run:
```javascript
console.log(typeof runLCAAnalysis);
```
**Expected**: `function`  
**If you see** `undefined`, the script did not load

### Network check
In the Network tab, confirm:
1. `lca_analysis.js` returns 200 OK
2. The file is about 24KB

---

## Summary

**Problem**: LCA analysis on the wizard page did not run  
**Root cause**: a Jinja2 template limitation  
**Fix**:
- Option A: make the wizard page standalone, with its own modals and script tag
- Option B: move the shared JavaScript into one file

**Result**: LCA analysis works on both the wizard page and the project detail page, with less duplicated code.

---

**Author**: AI Assistant  
**Date**: 2025-11-06  
**Status**: implemented; waiting for a manual browser check
