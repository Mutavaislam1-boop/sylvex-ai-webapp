import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, existsSync} from 'node:fs';
import vm from 'node:vm';

const path = existsSync(new URL('../webapp/js/cabinet.js', import.meta.url))
  ? '../webapp/js/cabinet.js' : '../studio/js/website-studio.js';
const source = readFileSync(new URL(path, import.meta.url), 'utf8');
function fn(name) {
  const match = new RegExp('^[ \\t]*(?:async )?function ' + name + '\\(', 'm').exec(source);
  assert.ok(match, name + ' exists');
  let depth = 0;
  for (let i = source.indexOf('{', match.index); i < source.length; i++) {
    if (source[i] === '{') depth++;
    if (source[i] === '}' && --depth === 0) return source.slice(match.index, i + 1);
  }
  assert.fail('Unclosed function: ' + name);
}
const escapeHtml = value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;');
function context(extra = {}) {
  return vm.createContext({URLSearchParams, window:{}, imageState:{uploadedImageUrls:[]}, uploadLimitForTarget:()=>4, S:{escapeHtml, tg:null}, getTelegramId:()=>777,
    generationActionIcon:()=>'', ...extra});
}
function load(ctx, ...names) { vm.runInContext(names.map(fn).join('\n'), ctx); return ctx; }

test('completed downloads select the requested image; ZIP keeps the existing authenticated route', () => {
  const ctx = load(context(), 'completedGenerationDownloadUrl', 'generationDownloadFilename', 'renderCompletedGenerationDownload');
  const selected = ctx.renderCompletedGenerationDownload('job-four', 'completed', '', 'image', 2);
  assert.match(selected, /result_index=2/);
  assert.match(selected, /data-selected-generation-download/);
  const archive = ctx.renderCompletedGenerationDownload('job-four', 'completed', '', 'image', 0, true);
  assert.match(archive, /download_all=true/);
  assert.match(archive, /Скачать все/);
  assert.match(archive, /\.zip/);
  assert.doesNotMatch(archive, /data-selected-generation-download/);
  assert.match(selected, /telegram_id=777/);
  assert.equal(ctx.renderCompletedGenerationDownload('job-four', 'processing', '', 'image', 0, true), '');
});

test('changing the selected image updates its download and reuse; never changes Download all', () => {
  const selected = {dataset:{downloadUrl:'old'}};
  const open = {dataset:{imageUrl:'first'}};
  const reuse = {dataset:{imageUrl:'first'}};
  const archive = {dataset:{downloadUrl:'zip-unchanged'}};
  const drawer = {dataset:{generationJobId:'job-four'}, querySelector:()=>selected,
    querySelectorAll:()=>[open,reuse]};
  const ctx = load(context({document:{getElementById:()=>drawer}}),
    'completedGenerationDownloadUrl', 'syncGenerationInfoImage');
  ctx.syncGenerationInfoImage('third', 'job-four', 2);
  assert.match(selected.dataset.downloadUrl, /result_index=2/);
  assert.equal(open.dataset.imageUrl, 'third');
  assert.equal(reuse.dataset.imageUrl, 'third');
  assert.equal(archive.dataset.downloadUrl, 'zip-unchanged');
  ctx.syncGenerationInfoImage('other', 'another-job', 0);
  assert.equal(reuse.dataset.imageUrl, 'third', 'another job cannot retarget the open drawer');
});

test('image viewer carries job identity and tracks the swiped image index', () => {
  const download = {dataset:{}, hidden:true};
  const image = {};
  const counter = {};
  const viewer = {classList:{toggle(){}},querySelector:()=>download};
  const selected=[];
  const ctx = load(context({imageViewerUrls:['one','two','three','four'],imageViewerIndex:2,
    imageViewerDownloadJobId:'job-four',imageViewerDownloadProjectId:'',imageViewerDownloadNodeId:'',
    document:{getElementById:id=>({imageViewer:viewer,imageViewerImg:image,imageViewerCounter:counter}[id])},
    syncGenerationInfoImage:(...args)=>selected.push(args)}),
    'completedGenerationDownloadUrl','generationDownloadFilename','renderImageViewerImage');
  ctx.renderImageViewerImage();
  assert.equal(image.src,'three');
  assert.equal(counter.textContent,'3 / 4');
  assert.equal(download.hidden,false);
  assert.match(download.dataset.downloadUrl,/result_index=2/);
  assert.deepEqual(selected[0],['three','job-four',2]);
});

test('result card and drawer wire real job identity into image previews', () => {
  assert.match(fn('renderImageResultMiniCard'), /data-generation-job-id/);
  const drawer = fn('openGenerationInfoDrawer');
  assert.match(drawer,/data-generation-job-id/);
  assert.doesNotMatch(drawer,/renderCompletedGenerationDownload\(jobId, generationStatus, '', type, 0, true\)/);
  assert.match(drawer,/useGenerationImageAsReference/);
  assert.doesNotMatch(drawer,/restoreImageStateFromGenerationMetadata\(/);
});

test('reuse adds the selected existing URL to the image draft without uploading or generating', () => {
  const calls=[];
  const ctx=load(context({studioMode:'image',UPLOAD_TARGETS:{IMAGE_UPLOAD:'image'},
    setUploadTarget:value=>calls.push(['target',value]),
    selectGeneratedImage:(event,url)=>calls.push(['reference',url]),
    closeGenerationInfoDrawer:()=>calls.push(['close']),closeImageViewer:()=>{},
    updateComposerMode:()=>assert.fail('existing model/settings must remain'),
    fetch:()=>assert.fail('no provider call or upload'),toast:()=>{}}), 'useGenerationImageAsReference');
  ctx.useGenerationImageAsReference({preventDefault(){},stopPropagation(){},currentTarget:{dataset:{imageUrl:'/api/public/storage/generated/third.png'}}});
  assert.deepEqual(calls,[['target','image'],['reference','/api/public/storage/generated/third.png'],['close']]);
});

test('reuse respects a locked non-image generation instead of attaching to the wrong mode', () => {
  const ctx=load(context({studioMode:'video',updateComposerMode:()=>{},toast:()=>{},
    setUploadTarget:()=>assert.fail('mode switch was blocked'),selectGeneratedImage:()=>assert.fail('must not alter video draft')}),
    'useGenerationImageAsReference');
  ctx.useGenerationImageAsReference({preventDefault(){},stopPropagation(){},currentTarget:{dataset:{imageUrl:'third'}}});
});


test('each chosen photo has its own single-file route, including the first and last result', () => {
  const ctx = load(context(), 'completedGenerationDownloadUrl', 'generationDownloadFilename', 'renderCompletedGenerationDownload');
  const urls = new Set();
  for (let index = 0; index < 4; index++) {
    const url = new URL(ctx.completedGenerationDownloadUrl('job-four', index), 'https://api.example.test');
    assert.equal(Number(url.searchParams.get('result_index') || 0), index);
    assert.equal(url.searchParams.has('download_all'), false);
    urls.add(url.toString());
    assert.doesNotMatch(ctx.renderCompletedGenerationDownload('job-four', 'completed', '', 'image', index), /\.zip|download_all/);
  }
  assert.equal(urls.size, 4);
});

test('Grid with one result retains the direct individual download', () => {
  const node={id:'one',generation_id:'job-one',output:{type:'image',items:[{url:'one.png'}],selected_index:0}},calls=[];
  const ctx=load(context({loadStudioGridState:()=>({nodes:[node]}),triggerStudioGridDownload:(...args)=>calls.push(args),
    openGenerationImageDownloadPicker:()=>assert.fail('one image needs no chooser')}),'downloadStudioGridNode');
  ctx.downloadStudioGridNode('one');assert.equal(calls.length,1);assert.equal(calls[0][0],node);assert.equal(calls[0][1],0);
});
