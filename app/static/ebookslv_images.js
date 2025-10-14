(function(){
  'use strict';
  const MODAL_ID = 'ebookslv-images-modal';
  const GRID_CLASS = 'ebookslv-images-grid';
  const STATUS_CLASS = 'ebookslv-image-status';

  function ensureStyles(){
    if(document.getElementById('ebookslv-images-style')) return;
    const style = document.createElement('style');
    style.id = 'ebookslv-images-style';
    style.textContent = `
      #${MODAL_ID}{position:fixed;top:0;left:0;width:100%;height:100%;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,0.55);z-index:1050;}
      #${MODAL_ID}.visible{display:flex;}
      #${MODAL_ID} .modal-content{background:#fff;max-width:800px;width:90%;max-height:90%;overflow:auto;border-radius:6px;box-shadow:0 4px 20px rgba(0,0,0,0.3);padding:16px;}
      #${MODAL_ID} .modal-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;}
      #${MODAL_ID} .modal-header h3{margin:0;font-size:18px;}
      #${MODAL_ID} .modal-body{display:flex;flex-direction:column;gap:16px;}
      .${GRID_CLASS}{display:grid;grid-template-columns:repeat(auto-fill, minmax(120px, 1fr));gap:12px;}
      .${GRID_CLASS} figure{margin:0;border:1px solid #dedede;border-radius:4px;padding:8px;display:flex;flex-direction:column;gap:6px;align-items:center;}
      .${GRID_CLASS} img{max-width:100%;max-height:140px;object-fit:cover;border-radius:4px;}
      .${STATUS_CLASS}{font-size:11px;padding:2px 6px;border-radius:3px;background:#e7e7e7;color:#333;text-transform:uppercase;letter-spacing:0.5px;}
      .${STATUS_CLASS}.uploaded{background:#d4edda;color:#256029;}
      .${STATUS_CLASS}.pending{background:#fff3cd;color:#856404;}
      .${STATUS_CLASS}.local{background:#f8d7da;color:#721c24;}
      #${MODAL_ID} .upload-box{border:2px dashed #a0a0a0;border-radius:6px;padding:20px;text-align:center;cursor:pointer;transition:border-color .2s;}
      #${MODAL_ID} .upload-box.dragover{border-color:#428bca;}
      #${MODAL_ID} .actions{display:flex;gap:8px;}
      #${MODAL_ID} .error-msg{color:#d9534f;font-size:13px;}
      #${MODAL_ID} .spinner{width:20px;height:20px;border:3px solid #e0e0e0;border-top-color:#428bca;border-radius:50%;animation:spin 1s linear infinite;margin:0 auto;}
      @keyframes spin{to{transform:rotate(360deg);}}
    `;
    document.head.appendChild(style);
  }

  function createModal(){
    ensureStyles();
    let modal = document.getElementById(MODAL_ID);
    if(modal) return modal;
    modal = document.createElement('div');
    modal.id = MODAL_ID;
    modal.innerHTML = `
      <div class="modal-content">
        <div class="modal-header">
          <h3>Book Images</h3>
          <button type="button" class="btn btn-default btn-sm" data-dismiss="modal">Close</button>
        </div>
        <div class="modal-body">
          <div class="upload-section">
            <div class="upload-box" tabindex="0">Drop image or click to select</div>
            <input type="file" accept="image/jpeg,image/png,image/webp" style="display:none" />
            <div class="error-msg" aria-live="polite"></div>
          </div>
          <div class="images-section">
            <div class="spinner" hidden></div>
            <div class="${GRID_CLASS}"></div>
          </div>
        </div>
      </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', ev => {
      if(ev.target === modal) hideModal();
    });
    modal.querySelector('[data-dismiss="modal"]').addEventListener('click', hideModal);
    const uploadBox = modal.querySelector('.upload-box');
    const fileInput = modal.querySelector('input[type="file"]');
    uploadBox.addEventListener('click', () => fileInput.click());
    uploadBox.addEventListener('keypress', ev => {
      if(ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        fileInput.click();
      }
    });
    ['dragenter','dragover'].forEach(evt => uploadBox.addEventListener(evt, ev => {
      ev.preventDefault();
      ev.dataTransfer.dropEffect = 'copy';
      uploadBox.classList.add('dragover');
    }));
    ['dragleave','drop'].forEach(evt => uploadBox.addEventListener(evt, () => uploadBox.classList.remove('dragover')));
    uploadBox.addEventListener('drop', ev => {
      ev.preventDefault();
      if(ev.dataTransfer.files && ev.dataTransfer.files[0]){
        fileInput.files = ev.dataTransfer.files;
        triggerUpload();
      }
    });
    fileInput.addEventListener('change', triggerUpload);

    function triggerUpload(){
      if(!fileInput.files || !fileInput.files[0]) return;
      const file = fileInput.files[0];
      const ctx = getState();
      if(!ctx) return;
      uploadImage(ctx, file);
      fileInput.value = '';
    }

    return modal;
  }

  let currentState = null;

  function setState(state){ currentState = state; }
  function getState(){ return currentState; }

  function showModal(state){
    const modal = createModal();
    setState(state);
    modal.classList.add('visible');
    modal.querySelector('.modal-header h3').textContent = `Book ${state.bookId} – ${state.title || ''}`;
    modal.querySelector('.error-msg').textContent = '';
    renderImages([]);
    loadImages(state);
  }

  function hideModal(){
    const modal = document.getElementById(MODAL_ID);
    if(modal){
      modal.classList.remove('visible');
      setState(null);
    }
  }

  function renderImages(images){
    const modal = document.getElementById(MODAL_ID);
    if(!modal) return;
    const grid = modal.querySelector('.'+GRID_CLASS);
    grid.innerHTML = '';
    if(!images.length){
      const empty = document.createElement('p');
      empty.textContent = 'No extra images yet.';
      grid.appendChild(empty);
      return;
    }
    const frag = document.createDocumentFragment();
    images.forEach(img => {
      const figure = document.createElement('figure');
      figure.innerHTML = `
        <img loading="lazy" src="${img.url}" alt="${img.name}">
        <figcaption style="width:100%;display:flex;flex-direction:column;gap:4px;align-items:center;">
          <span style="font-size:12px;word-break:break-all;text-align:center;">${img.name}</span>
          <div class="actions">
            <span class="${STATUS_CLASS} ${statusClass(img.status)}">${img.status}</span>
            <button type="button" class="btn btn-xs btn-danger" data-delete="${img.name}">Delete</button>
          </div>
        </figcaption>`;
      frag.appendChild(figure);
    });
    grid.appendChild(frag);
  }

  function statusClass(status){
    if(status === 'uploaded') return 'uploaded';
    if(status === 'pending') return 'pending';
    return 'local';
  }

  function setLoading(isLoading){
    const modal = document.getElementById(MODAL_ID);
    if(!modal) return;
    const spinner = modal.querySelector('.spinner');
    spinner.hidden = !isLoading;
  }

  function handleError(msg){
    const modal = document.getElementById(MODAL_ID);
    if(!modal) return;
    modal.querySelector('.error-msg').textContent = msg || '';
  }

  async function loadImages(state){
    setLoading(true);
    try {
      const res = await fetch(`/admin/ebookslv/books/${state.bookId}/images/list`, {credentials:'same-origin'});
      if(!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const files = data.images || data.files || [];
      const decorated = files.map(f => ({
        name: f.name,
        url: `/ebookslv/book/${state.bookId}/image/${encodeURIComponent(f.name)}`,
        status: f.uploaded_remote ? 'uploaded' : (f.pending_remote ? 'pending' : 'local'),
        remote_uid: f.remote_uid
      }));
      renderImages(decorated);
      wireDeleteButtons(state);
    } catch(err){
      handleError(`Failed to load images: ${err.message || err}`);
    } finally {
      setLoading(false);
    }
  }

  function wireDeleteButtons(state){
    const modal = document.getElementById(MODAL_ID);
    if(!modal) return;
    modal.querySelectorAll('[data-delete]').forEach(btn => {
      btn.addEventListener('click', async () => {
        if(!confirm('Delete this image?')) return;
        const name = btn.getAttribute('data-delete');
        if(!name) return;
        setLoading(true);
        try {
          const url = new URL(`/admin/ebookslv/books/${state.bookId}/images/${encodeURIComponent(name)}`, window.location.origin);
          const remote = btn.closest('figure').querySelector(`.${STATUS_CLASS}`)?.classList.contains('uploaded');
          if(remote) url.searchParams.set('remote','1');
          const res = await fetch(url.toString(), {method:'DELETE', credentials:'same-origin'});
          if(!res.ok) throw new Error(`HTTP ${res.status}`);
          await res.json();
          loadImages(state);
        } catch(err){
          handleError(`Delete failed: ${err.message || err}`);
        } finally {
          setLoading(false);
        }
      });
    });
  }

  async function uploadImage(state, file){
    handleError('');
    setLoading(true);
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch(`/admin/ebookslv/books/${state.bookId}/images/upload`, {
        method: 'POST',
        body: form,
        credentials: 'same-origin'
      });
      const data = await res.json();
      if(!res.ok || data.error){
        throw new Error(data.error || `HTTP ${res.status}`);
      }
      loadImages(state);
    } catch(err){
      handleError(`Upload failed: ${err.message || err}`);
    } finally {
      setLoading(false);
    }
  }

  document.addEventListener('click', ev => {
    const target = ev.target;
    if(!(target instanceof Element)) return;
    const dataset = target.dataset;
    if(dataset.images){
      const bookId = Number(dataset.images);
      const title = dataset.title || target.getAttribute('data-title') || target.getAttribute('aria-label') || '';
      showModal({bookId, title});
    }
  });
})();
