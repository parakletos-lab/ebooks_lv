(function(){
  'use strict';
  function getBookId(){
    const match = window.location.pathname.match(/\/book\/(\d+)/);
    return match ? Number(match[1]) : null;
  }

  function ensureStyles(){
    if(document.getElementById('ebookslv-gallery-style')) return;
    const style = document.createElement('style');
    style.id = 'ebookslv-gallery-style';
    style.textContent = `
      .ebookslv-gallery{margin-top:24px;}
      .ebookslv-gallery h3{margin-bottom:12px;font-size:18px;}
      .ebookslv-gallery-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:12px;}
      .ebookslv-gallery-grid a{display:block;border:1px solid #dedede;border-radius:6px;overflow:hidden;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,0.08);transition:transform .2s;}
      .ebookslv-gallery-grid a:hover{transform:scale(1.02);}
      .ebookslv-gallery-grid img{width:100%;height:140px;object-fit:cover;display:block;}
      .ebookslv-lightbox{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.8);display:flex;align-items:center;justify-content:center;z-index:1050;}
      .ebookslv-lightbox img{max-width:90%;max-height:90%;box-shadow:0 4px 20px rgba(0,0,0,.4);border-radius:6px;}
    `;
    document.head.appendChild(style);
  }

  function createGallery(images, bookId){
    ensureStyles();
    const container = document.createElement('section');
    container.className = 'ebookslv-gallery';
    container.innerHTML = '<h3>Gallery</h3>';
    const grid = document.createElement('div');
    grid.className = 'ebookslv-gallery-grid';
    images.forEach(img => {
      const link = document.createElement('a');
      link.href = `/ebookslv/book/${bookId}/image/${encodeURIComponent(img.name)}`;
      link.dataset.full = link.href;
      link.innerHTML = `<img loading="lazy" alt="${img.name}" src="${link.href}">`;
      grid.appendChild(link);
    });
    container.appendChild(grid);
    return container;
  }

  function attachLightbox(container){
    container.addEventListener('click', function(ev){
      const anchor = ev.target.closest('a');
      if(!anchor) return;
      ev.preventDefault();
      const overlay = document.createElement('div');
      overlay.className = 'ebookslv-lightbox';
      const img = document.createElement('img');
      img.src = anchor.dataset.full;
      overlay.appendChild(img);
      overlay.addEventListener('click', () => overlay.remove());
      document.body.appendChild(overlay);
    });
  }

  async function init(){
    const bookId = getBookId();
    if(!bookId) return;
    try {
      const res = await fetch(`/ebookslv/book/${bookId}/images.json`, {credentials:'same-origin'});
      if(!res.ok) return;
      const data = await res.json();
      const images = Array.isArray(data.images) ? data.images : [];
      if(!images.length) return;
      const cover = document.getElementById('detailcover');
      if(!cover) return;
      const target = cover.closest('.col-sm-3')?.parentNode;
      const gallery = createGallery(images, bookId);
      if(target && target.parentNode){
        target.parentNode.insertBefore(gallery, target.nextSibling);
      } else {
        document.querySelector('.single .row')?.appendChild(gallery);
      }
      attachLightbox(gallery);
    } catch(err){
      console.warn('ebookslv gallery failed', err);
    }
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
