// Run with: node --test tests/test_grid_video_input_propagation.mjs
//
// Regression tests for a standalone fix (not part of Phase 1 Batch 8's
// gridModelsForType filtering work - see
// /root/.claude/plans/splendid-moseying-starlight.md): a Grid video node's
// 'video' input port (GRID_TYPES.video.inputs includes 'video', for
// chaining an upstream video node's output into video_edit/motion_control
// mode) could be connected via the UI, and resolveGridNodeInputs()
// correctly resolved the connected edge into inputs.video - but two
// consumers of that resolved value ignored it entirely:
//
// 1. gridGenerationPayload()'s video branch built video_url only from
//    attachedVideos[0] (a locally attached file), never from
//    inputs.video?.value - so a connected upstream video was silently
//    dropped at dispatch time even though it was present in `inputs`.
// 2. validateGridNodeInputs() only checked hasVideo from local
//    attachments, and only gated on it for mode==='video_edit' -
//    motion_control wasn't checked for a video source at all, so a node
//    with neither an attachment nor a connection would pass validation
//    and dispatch with an empty video source.
//
// Both are fixed here: gridGenerationPayload now resolves
// input_video/video_url from inputs.video?.value.url (or .preview_url)
// first, falling back to attachedVideos[0] only when no connection
// exists - the same precedence the image port already had. validateGridNodeInputs
// now treats inputs.video?.value as a valid source and checks it for both
// video_edit and motion_control. image_to_video/text_to_video are
// unaffected - the image port's own resolution is untouched, and
// text_to_video has never required a video source.
//
// Connections also invalidate only their target branch. Invalidating every
// descendant of the source used to mark a completed image sibling READY when
// text was connected to the same video node, making its image reference vanish.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');

function extractFunction(name) {
  const pattern = new RegExp(`^([ \\t]*)(?:async )?function ${name}\\(`, 'm');
  const match = pattern.exec(cabinet);
  assert.ok(match, `declaration not found: ${name}`);
  const openIndex = cabinet.indexOf('{', match.index);
  let depth = 0;
  let i = openIndex;
  for (; i < cabinet.length; i++) {
    if (cabinet[i] === '{') depth++;
    else if (cabinet[i] === '}') { depth--; if (depth === 0) break; }
  }
  assert.ok(i < cabinet.length, `matching close not found: ${name}`);
  return cabinet.slice(match.index, i + 1);
}

function extractVideoModelConfigWithKling() {
  const startMatch = /const VIDEO_MODEL_CONFIG *= *\{/.exec(cabinet);
  assert.ok(startMatch, 'VIDEO_MODEL_CONFIG declaration not found');
  const assignMatch = /Object\.assign\(VIDEO_MODEL_CONFIG, *\{/.exec(cabinet);
  assert.ok(assignMatch, 'Object.assign(VIDEO_MODEL_CONFIG, ...) not found');
  const openIndex = cabinet.indexOf('{', assignMatch.index);
  let depth = 0;
  let i = openIndex;
  for (; i < cabinet.length; i++) {
    if (cabinet[i] === '{') depth++;
    else if (cabinet[i] === '}') { depth--; if (depth === 0) break; }
  }
  let j = i + 1;
  while (cabinet[j] !== ')') j++;
  assert.ok(j < cabinet.length, 'matching close not found for Object.assign(VIDEO_MODEL_CONFIG, ...)');
  return cabinet.slice(startMatch.index, j + 1) + ';';
}

function buildPayloadContext() {
  const context = vm.createContext({
    providerHintForModel: () => 'kling',
    gridDefaultModel: () => 'seedance_2_fast',
    fetchedModelCapabilities: null,
    getTelegramId: () => 0,
    uiLang: () => 'ru',
    loadStudioGridState: () => ({projectId: 'grid_project_test'}),
  });
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractFunction('gridVideoCapability'), context);
  vm.runInContext(extractFunction('gridVideoRequestPlan'), context);
  vm.runInContext(extractFunction('gridGenerationPayload'), context);
  return context;
}

function runPayload(context, node, inputs) {
  vm.runInContext('__node = ' + JSON.stringify(node) + ';', context);
  vm.runInContext('__inputs = ' + JSON.stringify(inputs) + ';', context);
  return vm.runInContext('gridGenerationPayload(__node, __inputs)', context);
}

const baseVideoNode = (overrides) => Object.assign({
  id: 'grid_video_1',
  type: 'video',
  model: 'kling_motion_3_0',
  prompt: 'test prompt',
  settings: {generation_mode: 'motion_control'},
  attachments: [],
}, overrides);

test('gridGenerationPayload: connected video reaches both video_url and input_video', () => {
  const context = buildPayloadContext();
  const node = baseVideoNode();
  const inputs = {
    effective_prompt: {value: 'test prompt'},
    video: {value: {url: 'https://cdn.example.com/connected.mp4', type: 'video'}},
  };
  const payload = runPayload(context, node, inputs);
  assert.equal(payload.video_options.video_url, 'https://cdn.example.com/connected.mp4');
  assert.equal(payload.video_options.input_video, 'https://cdn.example.com/connected.mp4');
});

test('gridGenerationPayload: connected video falls back to preview_url when url is absent', () => {
  const context = buildPayloadContext();
  const node = baseVideoNode();
  const inputs = {
    effective_prompt: {value: 'test prompt'},
    video: {value: {preview_url: 'https://cdn.example.com/connected-preview.mp4', type: 'video'}},
  };
  const payload = runPayload(context, node, inputs);
  assert.equal(payload.video_options.video_url, 'https://cdn.example.com/connected-preview.mp4');
  assert.equal(payload.video_options.input_video, 'https://cdn.example.com/connected-preview.mp4');
});

test('gridGenerationPayload: local attachment still works as a fallback when nothing is connected', () => {
  const context = buildPayloadContext();
  const node = baseVideoNode({attachments: [{kind: 'video', url: 'https://cdn.example.com/attached.mp4'}]});
  const inputs = {effective_prompt: {value: 'test prompt'}};
  const payload = runPayload(context, node, inputs);
  assert.equal(payload.video_options.video_url, 'https://cdn.example.com/attached.mp4');
  assert.equal(payload.video_options.input_video, 'https://cdn.example.com/attached.mp4');
});

test('gridGenerationPayload: connected video takes precedence over a local attachment when both exist', () => {
  const context = buildPayloadContext();
  const node = baseVideoNode({attachments: [{kind: 'video', url: 'https://cdn.example.com/attached.mp4'}]});
  const inputs = {
    effective_prompt: {value: 'test prompt'},
    video: {value: {url: 'https://cdn.example.com/connected.mp4', type: 'video'}},
  };
  const payload = runPayload(context, node, inputs);
  assert.equal(payload.video_options.video_url, 'https://cdn.example.com/connected.mp4');
  assert.equal(payload.video_options.input_video, 'https://cdn.example.com/connected.mp4');
});

test('gridGenerationPayload: no connection and no attachment leaves video_url/input_video empty', () => {
  const context = buildPayloadContext();
  const node = baseVideoNode();
  const inputs = {effective_prompt: {value: 'test prompt'}};
  const payload = runPayload(context, node, inputs);
  assert.equal(payload.video_options.video_url, '');
  assert.equal(payload.video_options.input_video, '');
});

test('gridGenerationPayload: image_to_video is unaffected by the video-input change (image resolution untouched)', () => {
  const context = buildPayloadContext();
  const node = baseVideoNode({model: 'seedance_2_fast', settings: {generation_mode: 'image_to_video'}});
  const inputs = {
    effective_prompt: {value: 'test prompt'},
    image: {value: {url: 'https://cdn.example.com/character.jpg'}},
  };
  const payload = runPayload(context, node, inputs);
  assert.equal(payload.video_options.start_image, 'https://cdn.example.com/character.jpg');
  assert.equal(payload.video_options.image_url, 'https://cdn.example.com/character.jpg');
  assert.equal(payload.video_options.video_url, '');
  assert.equal(payload.video_options.generation_mode, 'image_to_video');
});

for (const model of ['luma_ray_v3_2', 'pixverse_v6', 'heygen_image_video', 'runway_gen4_5']) {
  test(`gridGenerationPayload: ${model} sends a connected image once as the start frame`, () => {
    const context = buildPayloadContext();
    const node = baseVideoNode({model, settings: {generation_mode: 'text_to_video'}});
    const inputs = {
      effective_prompt: {value: 'animate the character'},
      image: {value: {url: 'https://cdn.example.com/character.jpg'}},
    };
    const payload = runPayload(context, node, inputs);
    assert.equal(payload.video_options.start_image, 'https://cdn.example.com/character.jpg');
    assert.equal(payload.video_options.generation_mode, 'image_to_video');
    assert.deepEqual(Array.from(payload.video_options.reference_images), []);
    assert.deepEqual(Array.from(payload.video_options.referenceImageUrls), []);
  });
}

test('gridGenerationPayload: Grid text nodes request direct artifact output', () => {
  const context = buildPayloadContext();
  const payload = runPayload(context, {
    id: 'grid_text_1', type: 'text', model: 'gpt-5.5', prompt: 'Write lyrics', settings: {}, attachments: [],
  }, {effective_prompt: {value: 'Write lyrics'}});
  assert.equal(payload.text_options.grid_direct_output, true);
});

test('gridGenerationPayload: text_to_video is unaffected (no video source required or sent)', () => {
  const context = buildPayloadContext();
  const node = baseVideoNode({model: 'seedance_2_fast', settings: {generation_mode: 'text_to_video'}});
  const inputs = {effective_prompt: {value: 'test prompt'}};
  const payload = runPayload(context, node, inputs);
  assert.equal(payload.video_options.video_url, '');
  assert.equal(payload.video_options.input_video, '');
  assert.equal(payload.video_options.generation_mode, 'text_to_video');
});

// =====================================================================
// validateGridNodeInputs
// =====================================================================

function buildValidateContext() {
  const context = vm.createContext({
    VIDEO_MODEL_CONFIG: {kling_motion_3_0: {modes:['motion_control'], start_image:true}},
    fetchedModelCapabilities: null,
    gridDefaultModel: () => 'kling_motion_3_0',
  });
  vm.runInContext(extractFunction('gridVideoCapability'), context);
  vm.runInContext(extractFunction('gridVideoRequestPlan'), context);
  vm.runInContext(extractFunction('validateGridNodeInputs'), context);
  return context;
}

function runValidate(context, node, inputs) {
  vm.runInContext('__node = ' + JSON.stringify(node) + ';', context);
  vm.runInContext('__inputs = ' + JSON.stringify(inputs) + ';', context);
  return vm.runInContext('validateGridNodeInputs(__node, __inputs)', context);
}

test('validateGridNodeInputs: video_edit with a connected video (no attachment) passes validation', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'video_edit'}, attachments: []};
  const inputs = {
    effective_prompt: {value: 'edit this'},
    video: {value: {url: 'https://cdn.example.com/connected.mp4'}},
  };
  const result = runValidate(context, node, inputs);
  assert.equal(result.ok, true);
  assert.equal(result.missing.length, 0);
});

test('validateGridNodeInputs: video_edit with neither connected nor attached video fails', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'video_edit'}, attachments: []};
  const inputs = {effective_prompt: {value: 'edit this'}};
  const result = runValidate(context, node, inputs);
  assert.equal(result.ok, false);
  assert.ok(result.missing.includes('Исходное видео'));
});

// motion_control needs BOTH a video (motion/reference source) and an
// image (subject) - the Kling provider path's own requires_image gate
// (services/video_router.py's requires_image) includes motion_control
// alongside image_to_video, so a motion_control request with a video but
// no image would pass a video-only check here and still fail server-side.
test('validateGridNodeInputs: motion_control with a connected video AND a connected image passes validation', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'motion_control'}, attachments: []};
  const inputs = {
    effective_prompt: {value: 'apply this motion'},
    video: {value: {url: 'https://cdn.example.com/connected.mp4'}},
    image: {value: {url: 'https://cdn.example.com/subject.jpg'}},
  };
  const result = runValidate(context, node, inputs);
  assert.equal(result.ok, true);
  assert.equal(result.missing.length, 0);
});

test('validateGridNodeInputs: motion_control with a connected video but no image fails with the image message', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'motion_control'}, attachments: []};
  const inputs = {
    effective_prompt: {value: 'apply this motion'},
    video: {value: {url: 'https://cdn.example.com/connected.mp4'}},
  };
  const result = runValidate(context, node, inputs);
  assert.equal(result.ok, false);
  assert.ok(result.missing.includes('Исходное изображение'));
  assert.ok(!result.missing.includes('Исходное видео'));
});

test('validateGridNodeInputs: motion_control with a connected image but no video fails with the video message', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'motion_control'}, attachments: []};
  const inputs = {
    effective_prompt: {value: 'apply this motion'},
    image: {value: {url: 'https://cdn.example.com/subject.jpg'}},
  };
  const result = runValidate(context, node, inputs);
  assert.equal(result.ok, false);
  assert.ok(result.missing.includes('Исходное видео'));
  assert.ok(!result.missing.includes('Исходное изображение'));
});

test('validateGridNodeInputs: motion_control with neither video nor image fails with both messages', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'motion_control'}, attachments: []};
  const inputs = {effective_prompt: {value: 'apply this motion'}};
  const result = runValidate(context, node, inputs);
  assert.equal(result.ok, false);
  assert.ok(result.missing.includes('Исходное видео'));
  assert.ok(result.missing.includes('Исходное изображение'));
});

test('validateGridNodeInputs: motion_control with both required inputs supplied through local attachments passes', () => {
  const context = buildValidateContext();
  const node = {
    type: 'video',
    settings: {generation_mode: 'motion_control'},
    attachments: [
      {kind: 'video', url: 'https://cdn.example.com/attached.mp4'},
      {kind: 'image', url: 'https://cdn.example.com/attached.jpg'},
    ],
  };
  const inputs = {effective_prompt: {value: 'apply this motion'}};
  const result = runValidate(context, node, inputs);
  assert.equal(result.ok, true);
  assert.equal(result.missing.length, 0);
});

test('validateGridNodeInputs: video_edit with a local attachment only (no connection) still passes (fallback preserved)', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'video_edit'}, attachments: [{kind: 'video', url: 'https://cdn.example.com/attached.mp4'}]};
  const inputs = {effective_prompt: {value: 'edit this'}};
  const result = runValidate(context, node, inputs);
  assert.equal(result.ok, true);
});

test('validateGridNodeInputs: image_to_video is unaffected by the video-source check', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'image_to_video'}, attachments: []};
  const withImage = runValidate(context, node, {effective_prompt: {value: 'p'}, image: {value: {url: 'https://cdn.example.com/a.jpg'}}});
  assert.equal(withImage.ok, true);
  const withoutImage = runValidate(context, node, {effective_prompt: {value: 'p'}});
  assert.equal(withoutImage.ok, false);
  assert.ok(withoutImage.missing.includes('Исходное изображение'));
  assert.ok(!withoutImage.missing.includes('Исходное видео'));
});

test('validateGridNodeInputs: text_to_video never requires a video or image source', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'text_to_video'}, attachments: []};
  const result = runValidate(context, node, {effective_prompt: {value: 'a video about cats'}});
  assert.equal(result.ok, true);
  assert.equal(result.missing.length, 0);
});

function buildConnectionContext(state) {
  const context = vm.createContext({
    GRID_TYPES: {
      text: {title: 'Text', inputs:['text'], outputs:['text']},
      image: {title: 'Image', inputs:['text','image'], outputs:['image']},
      video: {title: 'Video', inputs:['text','image','video'], outputs:['video']},
      music: {title: 'Music', inputs:['text','lyrics'], outputs:['audio']},
    },
    VIDEO_MODEL_CONFIG: {}, fetchedModelCapabilities: null,
    gridDefaultModel: () => '', loadStudioGridState: () => state,
    toast: () => {}, saveStudioGridState: () => {}, renderStudioGrid: () => {},
  });
  for (const name of ['gridConnectionCompatible','gridConnectionCreatesCycle','getGridNodeOutputValue','resolveGridNodeInputs','gridVideoCapability','gridVideoRequestPlan','reconcileGridVideoMode','markStudioGridDownstreamStale','connectStudioGridNodes','disconnectStudioGridEdge']) {
    vm.runInContext(extractFunction(name), context);
  }
  return context;
}

test('Text → Music transfers completed text on the first connection', () => {
  const state = {nodes:[
    {id:'text-1',type:'text',title:'Lyrics',prompt:'write lyrics',status:'COMPLETED',output:{type:'text',value:'First line'}},
    {id:'music-1',type:'music',title:'Music',prompt:'',status:'IDLE',settings:{}},
  ],edges:[]};
  const context=buildConnectionContext(state);
  assert.equal(vm.runInContext("connectStudioGridNodes('text-1','text','music-1','text')",context),true);
  assert.equal(state.edges.length,1);
  assert.equal(state.nodes[1].inputs.text.value,'First line');
  assert.equal(state.nodes[1].inputs.effective_prompt.value,'First line');
});

test('input resolution stays direct and never inherits a grandparent through an intermediate block', () => {
  const state = {nodes:[
    {id:'text-1',type:'text',title:'Secret upstream',prompt:'grandparent text',status:'COMPLETED',output:{type:'text',value:'grandparent text'}},
    {id:'image-1',type:'image',title:'Rendered image',prompt:'',status:'COMPLETED',settings:{},output:{type:'image',items:[{url:'https://cdn.example.com/result.jpg'}],selected_index:0}},
    {id:'video-1',type:'video',title:'Video',prompt:'',status:'IDLE',model:'unknown',settings:{}},
  ],edges:[{id:'a',from:'text-1',fromPort:'text',to:'image-1',toPort:'text'}]};
  const context=buildConnectionContext(state);
  vm.runInContext("connectStudioGridNodes('image-1','image','video-1','image')",context);
  const inputs=state.nodes[2].inputs;
  assert.equal(inputs.image.source_node_id,'image-1');
  assert.equal(inputs.text,undefined);
  assert.equal(inputs.effective_prompt,undefined);
});

test('adding text to a video keeps its completed image reference connected', () => {
  const imageUrl='https://cdn.example.com/generated-reference.jpg';
  const state={nodes:[
    {id:'text-1',type:'text',title:'Video prompt',prompt:'write a video prompt',status:'COMPLETED',output:{type:'text',value:'Animate this product'}},
    {id:'image-1',type:'image',title:'Generated reference',prompt:'product photo',status:'COMPLETED',settings:{},output:{type:'image',items:[{url:imageUrl}],selected_index:0}},
    {id:'video-1',type:'video',title:'Video',prompt:'',status:'IDLE',model:'unknown',settings:{}},
  ],edges:[{id:'text-image',from:'text-1',fromPort:'text',to:'image-1',toPort:'text'}]};
  const context=buildConnectionContext(state);

  assert.equal(vm.runInContext("connectStudioGridNodes('image-1','image','video-1','image')",context),true);
  assert.equal(state.nodes[1].status,'COMPLETED');
  assert.equal(state.nodes[2].inputs.image.value.url,imageUrl);

  assert.equal(vm.runInContext("connectStudioGridNodes('text-1','text','video-1','text')",context),true);
  assert.equal(state.nodes[1].status,'COMPLETED');
  assert.equal(state.nodes[2].inputs.image.value.url,imageUrl);
  assert.equal(state.nodes[2].inputs.effective_prompt.value,'Animate this product');
});

test('disconnecting an image edge removes only that reference from the video input', () => {
  const state={nodes:[
    {id:'text-1',type:'text',title:'Prompt',status:'COMPLETED',output:{type:'text',value:'Animate the scene'}},
    {id:'image-1',type:'image',title:'Reference',status:'COMPLETED',output:{type:'image',items:[{url:'https://cdn.example.com/reference.jpg'}],selected_index:0}},
    {id:'video-1',type:'video',title:'Video',status:'COMPLETED',model:'unknown',settings:{},output:{type:'video',url:'https://cdn.example.com/video.mp4'}},
    {id:'video-2',type:'video',title:'Next video',status:'COMPLETED',model:'unknown',settings:{},output:{type:'video',url:'https://cdn.example.com/next.mp4'}},
  ],edges:[
    {id:'text-video',from:'text-1',fromPort:'text',to:'video-1',toPort:'text'},
    {id:'image-video',from:'image-1',fromPort:'image',to:'video-1',toPort:'image'},
    {id:'video-next',from:'video-1',fromPort:'video',to:'video-2',toPort:'video'},
  ]};
  const context=buildConnectionContext(state);
  vm.runInContext("resolveGridNodeInputs('video-1')",context);
  assert.equal(state.nodes[2].inputs.image.value.url,'https://cdn.example.com/reference.jpg');

  assert.equal(vm.runInContext("disconnectStudioGridEdge('image-video')",context),true);
  assert.equal(state.nodes[2].inputs.image,undefined);
  assert.equal(state.nodes[2].inputs.effective_prompt.value,'Animate the scene');
  assert.equal(state.nodes[2].status,'READY');
  assert.equal(state.nodes[3].status,'READY');
  assert.ok(!state.edges.some(edge=>edge.id==='image-video'));
});
