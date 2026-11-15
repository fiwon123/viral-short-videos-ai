import {
  ACESFilmicToneMapping, AdditiveBlending, AmbientLight, AnimationMixer, BoxGeometry, Euler, PropertyBinding,
  Quaternion,
  BufferGeometry, CanvasTexture, CapsuleGeometry, Color, ConeGeometry, CylinderGeometry, DataTexture,
  DirectionalLight, DoubleSide, Float32BufferAttribute, Fog, FogExp2, HemisphereLight, Mesh, MeshBasicMaterial,
  MeshStandardMaterial, MeshToonMaterial, NearestFilter, NormalBlending, PCFShadowMap, PCFSoftShadowMap,
  PerspectiveCamera,
  PlaneGeometry, PMREMGenerator, PointLight, Points, PointsMaterial, RedFormat, Scene, SphereGeometry,
  SpotLight, SRGBColorSpace, TorusGeometry, Vector2, Vector3, WebGLRenderer,
} from "three";
import {RoomEnvironment} from "three/addons/environments/RoomEnvironment.js";
import {OutlineEffect} from "three/addons/effects/OutlineEffect.js";
import {GLTFLoader} from "three/addons/loaders/GLTFLoader.js";
import {clone} from "three/addons/utils/SkeletonUtils.js";
import {EffectComposer} from "three/addons/postprocessing/EffectComposer.js";
import {RenderPass} from "three/addons/postprocessing/RenderPass.js";
import {BokehPass} from "three/addons/postprocessing/BokehPass.js";
import {UnrealBloomPass} from "three/addons/postprocessing/UnrealBloomPass.js";
import {GTAOPass} from "three/addons/postprocessing/GTAOPass.js";
import {OutputPass} from "three/addons/postprocessing/OutputPass.js";
import {SMAAPass} from "three/addons/postprocessing/SMAAPass.js";
import {Font} from "three/addons/loaders/FontLoader.js";
import {TextGeometry} from "three/addons/geometries/TextGeometry.js";

import {lightingFor} from "./lighting.mjs";
import {easing, objectTrack, poseAt, poseTrack} from "./pose.mjs";

function randomizer(seed) {
  let state = (Number(seed) || 1) >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 2 ** 32;
  };
}

let spark = null;
function sparkTexture() {
  if (spark || typeof document === "undefined") return spark;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 64;
  const context = canvas.getContext("2d");
  const gradient = context.createRadialGradient(32, 32, 0, 32, 32, 30);
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.45, "rgba(255,255,255,.8)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, 64, 64);
  spark = new CanvasTexture(canvas);
  spark.colorSpace = SRGBColorSpace;
  return spark;
}

function toonRamp() {
  // Three hard bands: shadow, mid, lit. Shared by every toon material.
  const texture = new DataTexture(new Uint8Array([70, 160, 255]), 3, 1, RedFormat);
  texture.minFilter = texture.magFilter = NearestFilter;
  texture.needsUpdate = true;
  return texture;
}

function textTexture(text, {color = "#ffffff", font = "800 160px sans-serif"} = {}) {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  ctx.font = font;
  const width = Math.ceil(ctx.measureText(text).width) + 40;
  canvas.width = width;
  canvas.height = 220;
  ctx.font = font;
  ctx.textBaseline = "middle";
  ctx.lineWidth = 18;
  ctx.strokeStyle = "rgba(0,0,0,0.55)";
  ctx.strokeText(text, 20, 110);
  ctx.fillStyle = color;
  ctx.fillText(text, 20, 110);
  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  return {texture, aspect: canvas.width / canvas.height};
}

function makeMaterial(obj, ramp, extra = {}) {
  const common = {
    color: obj.color ?? "#ffffff",
    transparent: (obj.opacity ?? 1) < 1 || Boolean(extra.map),
    opacity: obj.opacity ?? 1,
    side: obj.double_sided || obj.kind === "plane" || obj.kind === "text" ? DoubleSide : undefined,
    ...extra,
  };
  if (obj.material === "basic") return new MeshBasicMaterial(common);
  if (obj.material === "toon") {
    return new MeshToonMaterial({...common, gradientMap: ramp,
      emissive: new Color(obj.emissive ?? "#000000"), emissiveIntensity: obj.emissive_intensity ?? 1});
  }
  return new MeshStandardMaterial({...common,
    metalness: obj.metalness ?? 0, roughness: obj.roughness ?? 0.62,
    emissive: new Color(obj.emissive ?? "#000000"), emissiveIntensity: obj.emissive_intensity ?? 1});
}

function findBone(node, name) {
  return node.getObjectByName(name) ?? node.getObjectByName(PropertyBinding.sanitizeNodeName(name));
}

// Value of a keyed IK target at progress: keys hold a point or an object (+ offset) and a weight.
function ikState(keys, progress, pointOf) {
  let before = {at: 0, point: pointOf(keys[0]), weight: 0};
  for (const key of keys) {
    const here = {at: key.at, point: pointOf(key), weight: key.weight ?? 1, ease: key.ease};
    if (progress <= key.at) {
      const t = key.at > before.at ? easing((progress - before.at) / (key.at - before.at), key.ease ?? "smooth") : 1;
      return {point: before.point.clone().lerp(here.point, t), weight: before.weight + (here.weight - before.weight) * t};
    }
    before = here;
  }
  return {point: before.point, weight: before.weight};
}

// Cyclic coordinate descent: rotate each joint (end to root) so the end bone points at the target.
function solveCCD(bones, target, iterations = 14) {
  const effector = bones[bones.length - 1];
  const joint = new Vector3(), end = new Vector3(), toEnd = new Vector3(), toTarget = new Vector3();
  const delta = new Quaternion(), world = new Quaternion(), parent = new Quaternion();
  for (let pass = 0; pass < iterations; pass += 1) {
    for (let index = bones.length - 2; index >= 0; index -= 1) {
      const bone = bones[index];
      bone.getWorldPosition(joint);
      effector.getWorldPosition(end);
      toEnd.subVectors(end, joint).normalize();
      toTarget.subVectors(target, joint).normalize();
      if (toEnd.lengthSq() < 1e-12 || toTarget.lengthSq() < 1e-12 || toEnd.dot(toTarget) > 0.99999) continue;
      delta.setFromUnitVectors(toEnd, toTarget);
      bone.getWorldQuaternion(world);
      bone.parent.getWorldQuaternion(parent);
      bone.quaternion.copy(parent.invert().multiply(delta.multiply(world)));
      bone.updateMatrixWorld(true);
    }
    effector.getWorldPosition(end);
    if (end.distanceTo(target) < 1e-4) break;
  }
}

export async function createThreeStage(specs, width, height, urlFor) {
  const renderer = new WebGLRenderer({alpha: true, antialias: true});
  renderer.setSize(width, height, false);
  renderer.setClearColor(0, 0);
  renderer.toneMapping = ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.outputColorSpace = SRGBColorSpace;
  renderer.shadowMap.enabled = Object.values(specs).some((spec) => spec.lighting?.shadows);
  // "high" quality anywhere switches the whole stage to soft shadows (the shadow type is renderer-wide).
  const highQuality = Object.values(specs).some((spec) => spec.quality === "high");
  renderer.shadowMap.type = highQuality ? PCFSoftShadowMap : PCFShadowMap;
  const shadowSize = highQuality ? 2048 : 1024;
  const geometries = {
    box: new BoxGeometry(1, 1, 1),
    sphere: new SphereGeometry(0.5, 36, 24),
    cylinder: new CylinderGeometry(0.5, 0.5, 1, 48),
    torus: new TorusGeometry(0.38, 0.12, 16, 48),
    plane: new PlaneGeometry(1, 1),
    cone: new ConeGeometry(0.5, 1, 48),
    capsule: new CapsuleGeometry(0.3, 0.4, 8, 24),
  };
  const ramp = toonRamp();
  const pmrem = new PMREMGenerator(renderer);
  let roomTexture = null;
  const loader = new GLTFLoader();
  const models = new Map();
  const fonts = new Map();
  const scenes = new Map();
  try {
    for (const [id, spec] of Object.entries(specs)) {
      const scene = new Scene();
      const light = lightingFor(spec);
      const key = new DirectionalLight(light.color, light.key);
      key.position.set(...light.position);
      key.target.position.set(...light.target);
      scene.add(new AmbientLight("#ffffff", light.ambient), key, key.target);
      if (light.shadowExtent !== null) {
        const extent = light.shadowExtent;
        key.castShadow = true;
        key.shadow.mapSize.set(shadowSize, shadowSize);
        if (highQuality) key.shadow.radius = 3;
        Object.assign(key.shadow.camera, {
          left: -extent, right: extent, top: extent, bottom: -extent,
          near: 0.01, far: key.position.distanceTo(key.target.position) + extent * 3,
        });
        key.shadow.camera.updateProjectionMatrix();
        key.shadow.normalBias = 0.015;
      }
      const lights = new Map();
      for (const item of spec.lights ?? []) {
        let node;
        if (item.kind === "point") {
          node = new PointLight(item.color ?? "#ffffff", item.intensity ?? 8, item.distance ?? 0, 2);
        } else if (item.kind === "spot") {
          node = new SpotLight(item.color ?? "#ffffff", item.intensity ?? 12, item.distance ?? 0,
            (item.angle ?? 30) * Math.PI / 180, item.penumbra ?? 0.35, 2);
          node.target.position.set(...(item.target ?? [0, 0, 0]));
          scene.add(node.target);
        } else {
          node = new HemisphereLight(item.color ?? "#cfe4ff", item.ground ?? "#3a2f28", item.intensity ?? 1);
        }
        if (item.position) node.position.set(...item.position);
        if (item.shadows && node.shadow) {
          node.castShadow = true;
          node.shadow.mapSize.set(shadowSize, shadowSize);
        }
        scene.add(node);
        lights.set(item.id, {node, spec: item});
      }
      if (spec.fog) {
        scene.fog = spec.fog.density
          ? new FogExp2(spec.fog.color, spec.fog.density)
          : new Fog(spec.fog.color, spec.fog.near ?? 4, spec.fog.far ?? 30);
      }
      if (spec.environment === "room") {
        roomTexture ??= pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
        scene.environment = roomTexture;
        scene.environmentIntensity = spec.environment_intensity ?? 0.6;
      }
      const camera = new PerspectiveCamera(spec.camera.fov ?? 37, width / height, 0.01, 2000);
      const objects = new Map();
      for (const obj of spec.objects) {
        let node;
        let animations = [];
        if (obj.kind === "glb") {
          if (!models.has(obj.file)) models.set(obj.file, await loader.loadAsync(urlFor(obj.file)));
          const model = models.get(obj.file);
          node = clone(model.scene);
          animations = model.animations ?? [];
        } else if (obj.kind === "text" && obj.depth && obj.typeface) {
          // Extruded text. Em size 0.727 matches the cap height of the flat text plane.
          if (!fonts.has(obj.typeface)) {
            fonts.set(obj.typeface, new Font(await (await fetch(urlFor(obj.typeface))).json()));
          }
          const bevel = obj.bevel ?? 0.3;
          const geometry = new TextGeometry(obj.text, {
            font: fonts.get(obj.typeface), size: 0.727, depth: obj.depth, curveSegments: 8,
            bevelEnabled: bevel > 0, bevelThickness: 0.05 * bevel, bevelSize: 0.03 * bevel, bevelSegments: 3,
          });
          geometry.center();
          node = new Mesh(geometry, makeMaterial({...obj, double_sided: false, kind: "extruded"}, ramp));
          node.userData.aspect = 1;
        } else if (obj.kind === "text") {
          const {texture, aspect} = textTexture(obj.text, {color: obj.color ?? "#ffffff",
            font: obj.font ?? "800 160px sans-serif"});
          node = new Mesh(geometries.plane, makeMaterial({...obj, color: "#ffffff"}, ramp,
            {map: texture, alphaTest: 0.02}));
          node.userData.aspect = aspect;
        } else {
          node = new Mesh(geometries[obj.kind], makeMaterial(obj, ramp));
        }
        if (light.shadowExtent !== null) {
          node.traverse((child) => {
            if (child.isMesh) {
              child.castShadow = obj.cast_shadow ?? false;
              child.receiveShadow = obj.receive_shadow ?? false;
            }
          });
        }
        scene.add(node);
        objects.set(obj.id, {node, spec: obj, animations});
      }
      const particleSystems = [];
      for (const particles of spec.particles ?? []) {
        const count = Math.min(5000, Number(particles.count ?? 60));
        const life = Number(particles.life ?? 1.2);
        const random = randomizer(particles.seed ?? 17);
        const positions = new Float32Array(count * 3);
        const data = [];
        for (let index = 0; index < count; index += 1) {
          const start = particles.start ?? (particles.emit === "continuous" ? random() * 12 : 0);
          data.push({
            start,
            offset: [
              (random() * 2 - 1) * (particles.spread?.[0] ?? 0),
              (random() * 2 - 1) * (particles.spread?.[1] ?? 0),
              (random() * 2 - 1) * (particles.spread?.[2] ?? 0),
            ],
            velocity: [
              (particles.velocity?.[0] ?? 0) * (0.75 + random() * 0.5),
              (particles.velocity?.[1] ?? 0) * (0.75 + random() * 0.5),
              (particles.velocity?.[2] ?? 0) * (0.75 + random() * 0.5),
            ],
          });
        }
        const geometry = new BufferGeometry();
        geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
        const material = new PointsMaterial({
          color: particles.color ?? "#ffffff",
          map: sparkTexture(),
          alphaTest: 0.02,
          size: particles.size ?? 0.04,
          transparent: true,
          opacity: particles.opacity ?? 0.8,
          depthWrite: false,
          sizeAttenuation: true,
          blending: particles.blending === "additive" ? AdditiveBlending : NormalBlending,
        });
        const points = new Points(geometry, material);
        points.frustumCulled = false;
        scene.add(points);
        particleSystems.push({points, data, spec: particles, life});
      }
      scenes.set(id, {scene, camera, lights, initialCamera: {
        position: spec.camera.position, target: spec.camera.target,
        fov: spec.camera.fov ?? 37,
      }, objects, particles: particleSystems});
    }
  } catch (error) {
    renderer.dispose();
    throw error;
  }

  return {
    compile(shot) {
      const {scene, camera, lights, initialCamera, objects, particles} = scenes.get(shot.scene);
      const lightTracks = Array.from(lights, ([id, {node, spec}]) => ({
        node,
        poses: poseTrack({intensity: spec.intensity ?? node.intensity, position: spec.position ?? [0, 0, 0]},
          (shot.lights ?? {})[id] ?? []),
      }));
      const outline = shot.outline
        ? new OutlineEffect(renderer, {defaultThickness: shot.outline.thickness ?? 0.006,
          defaultColor: new Color(shot.outline.color ?? "#111111").toArray()})
        : null;
      const cameraTrack = poseTrack(initialCamera, shot.camera);
      const duration = shot.duration ?? 1;
      const focusTrack = shot.focus?.length
        ? poseTrack({distance: 2, aperture: 1}, shot.focus) : null;
      const bloom = Number(shot.bloom ?? 0);
      const quality = shot.quality ?? specs[shot.scene]?.quality ?? "standard";
      let composer = null;
      let bokeh = null;
      if (focusTrack || bloom > 0 || quality === "high") {
        composer = new EffectComposer(renderer);
        composer.addPass(new RenderPass(scene, camera));
        if (quality === "high") {
          // Ambient occlusion grounds objects in contact shadows; it is the biggest step toward a rendered look.
          const ao = new GTAOPass(scene, camera, width, height);
          ao.blendIntensity = shot.ao ?? 1;
          composer.addPass(ao);
        }
        if (focusTrack) {
          bokeh = new BokehPass(scene, camera, {focus: 2, aperture: 0.0001, maxblur: 0.01});
          composer.addPass(bokeh);
        }
        if (bloom > 0) {
          composer.addPass(new UnrealBloomPass(
            new Vector2(width, height), bloom, shot.bloom_radius ?? 0.35,
            shot.bloom_threshold ?? 0.8));
        }
        if (quality === "high") {
          composer.addPass(new OutputPass());
          composer.addPass(new SMAAPass(width, height));
        }
      }
      const tracks = Array.from(objects, ([id, {node, spec, animations}]) => {
        const mixer = new AnimationMixer(node);
        const actions = [];
        for (const entry of (shot.animations?.[id] ?? [])) {
          const clip = animations.find((item) => item.name === entry.clip);
          if (!clip) continue;
          const action = mixer.clipAction(clip);
          action.play();
          action.setEffectiveWeight(entry.weight ?? 1);
          actions.push({action, clip, entry});
        }
        const keys = Object.hasOwn(shot.objects ?? {}, id) ? shot.objects[id] : [];
        const strip = (key, names) => Object.fromEntries(Object.entries(key).filter(([name]) => !names.includes(name)));
        const looks = keys.filter((key) => "opacity" in key || "emissive_intensity" in key);
        // Morph weights: one numeric track per target name, set on every mesh that has the target.
        const morphNames = [...new Set([...Object.keys(spec.morph ?? {}),
          ...keys.flatMap((key) => Object.keys(key.morph ?? {}))])];
        const morphMeshes = [];
        if (morphNames.length) node.traverse((child) => { if (child.morphTargetInfluences) morphMeshes.push(child); });
        const morphs = morphNames.length && morphMeshes.length ? {
          names: morphNames,
          meshes: morphMeshes,
          track: poseTrack(Object.fromEntries(morphNames.map((name) => [name, spec.morph?.[name] ?? 0])),
            keys.filter((key) => key.morph).map((key) => ({at: key.at, ease: key.ease, ...key.morph}))),
        } : null;
        // Bone offsets (degrees) on top of the rest pose or clip, and IK limbs.
        const boneNames = [...new Set([...Object.keys(spec.bones ?? {}),
          ...keys.flatMap((key) => Object.keys(key.bones ?? {}))])];
        const limbs = (shot.ik?.[id] ?? []).map((limb) => ({
          bones: limb.chain.map((name) => findBone(node, name)).filter(Boolean),
          keys: limb.keys,
        })).filter((limb) => limb.bones.length >= 2);
        const touched = new Map();
        for (const name of boneNames) {
          const bone = findBone(node, name);
          if (bone) touched.set(name, bone);
        }
        for (const limb of limbs) for (const bone of limb.bones) touched.set(bone.name, bone);
        const rest = new Map([...touched.values()].map((bone) => [bone, bone.quaternion.clone()]));
        const boneTrack = boneNames.length ? poseTrack(
          Object.fromEntries(boneNames.map((name) => [name, spec.bones?.[name] ?? [0, 0, 0]])),
          keys.filter((key) => key.bones).map((key) => ({at: key.at, ease: key.ease, ...key.bones}))) : null;
        return {
          node,
          morphs,
          rig: rest.size ? {rest, boneTrack, boneNames, touched, limbs} : null,
          aspect: node.userData.aspect ?? 1,
          poses: objectTrack(spec, keys.map((key) => strip(key, ["opacity", "emissive_intensity", "morph", "bones"]))),
          looks: looks.length ? poseTrack({opacity: spec.opacity ?? 1, emissive_intensity: spec.emissive_intensity ?? 1},
            looks.map((key) => ({at: key.at, ease: key.ease, ...("opacity" in key ? {opacity: key.opacity} : {}),
              ...("emissive_intensity" in key ? {emissive_intensity: key.emissive_intensity} : {})}))) : null,
          mixer: actions.length ? mixer : null,
          actions,
        };
      });
      const draw = (progress) => {
        const {position, target, fov} = poseAt(cameraTrack, progress);
        camera.position.set(...position);
        camera.lookAt(...target);
        if (fov !== undefined && camera.fov !== fov) {
          camera.fov = fov;
          camera.updateProjectionMatrix();
        }
        for (const {node, poses, looks, aspect, mixer, actions, morphs, rig} of tracks) {
          const pose = poseAt(poses, progress);
          node.visible = pose.visible;
          node.position.set(...pose.position);
          node.rotation.set(...pose.rotation);
          node.scale.set(pose.scale[0] * aspect, pose.scale[1], pose.scale[2]);
          if (looks && node.material) {
            const look = poseAt(looks, progress);
            node.material.transparent = true;
            node.material.opacity = look.opacity;
            if ("emissiveIntensity" in node.material) node.material.emissiveIntensity = look.emissive_intensity;
          }
          // Reset posed bones each frame so offsets never accumulate; the mixer then overwrites clip bones.
          if (rig) for (const [bone, quaternion] of rig.rest) bone.quaternion.copy(quaternion);
          if (mixer) {
            const now = progress * duration;
            for (const {action, clip, entry} of actions) {
              const offset = entry.at ?? 0;
              const span = Math.min(clip.duration, entry.duration ?? clip.duration);
              let time = (now - offset) * (entry.rate ?? 1);
              if (entry.loop === false) time = Math.max(0, Math.min(span, time));
              else time = ((time % span) + span) % span;
              action.time = time;
            }
            mixer.update(0);
          }
          // After the mixer, so keyed weights win over clips that also drive morphs.
          if (morphs) {
            const weights = poseAt(morphs.track, progress);
            for (const mesh of morphs.meshes) {
              for (const name of morphs.names) {
                const index = mesh.morphTargetDictionary?.[name] ?? (/^\d+$/.test(name) ? Number(name) : undefined);
                if (index !== undefined && index < mesh.morphTargetInfluences.length) {
                  mesh.morphTargetInfluences[index] = weights[name];
                }
              }
            }
          }
        }
        // Second pass once every object is posed, so IK can follow objects drawn later in the list.
        for (const {node, rig} of tracks) {
          if (rig) {
            if (rig.boneTrack) {
              const offsets = poseAt(rig.boneTrack, progress);
              for (const name of rig.boneNames) {
                const bone = rig.touched.get(name);
                const [x, y, z] = offsets[name].map((degrees) => degrees * Math.PI / 180);
                if (bone) bone.quaternion.multiply(new Quaternion().setFromEuler(new Euler(x, y, z)));
              }
            }
            node.updateMatrixWorld(true);
            for (const limb of rig.limbs) {
              const {point, weight} = ikState(limb.keys, progress, (key) => {
                if (key.object && objects.has(key.object)) {
                  const base = objects.get(key.object).node.getWorldPosition(new Vector3());
                  return base.add(new Vector3(...(key.offset ?? [0, 0, 0])));
                }
                return new Vector3(...(key.target ?? [0, 0, 0]));
              });
              if (weight <= 0) continue;
              const before = limb.bones.map((bone) => bone.quaternion.clone());
              solveCCD(limb.bones, point);
              if (weight < 1) {
                limb.bones.forEach((bone, index) => {
                  const solved = bone.quaternion.clone();
                  bone.quaternion.copy(before[index]).slerp(solved, weight);
                });
                node.updateMatrixWorld(true);
              }
            }
          }
        }
        for (const {node, poses} of lightTracks) {
          const look = poseAt(poses, progress);
          node.intensity = look.intensity;
          node.position.set(...look.position);
        }
        const now = progress * duration;
        for (const system of particles ?? []) {
          const {points, data, spec} = system;
          const array = points.geometry.attributes.position.array;
          for (let index = 0; index < data.length; index += 1) {
            const item = data[index];
            let start = item.start;
            if (spec.start === undefined && spec.emit === "continuous") start = item.start * duration;
            let local = now - start;
            if (spec.loop) local = ((local % system.life) + system.life) % system.life;
            const alive = local >= 0 && local <= system.life;
            const offset = index * 3;
            if (!alive) {
              array[offset] = 0;
              array[offset + 1] = -9999;
              array[offset + 2] = 0;
              continue;
            }
            const gravity = spec.gravity ?? [0, 0, 0];
            array[offset] = spec.position[0] + item.offset[0]
              + item.velocity[0] * local + 0.5 * gravity[0] * local * local;
            array[offset + 1] = spec.position[1] + item.offset[1]
              + item.velocity[1] * local + 0.5 * gravity[1] * local * local;
            array[offset + 2] = spec.position[2] + item.offset[2]
              + item.velocity[2] * local + 0.5 * gravity[2] * local * local;
          }
          points.geometry.attributes.position.needsUpdate = true;
        }
        if (composer) {
          if (bokeh) {
            const focus = poseAt(focusTrack, progress);
            bokeh.uniforms["focus"].value = focus.distance;
            bokeh.uniforms["aperture"].value = focus.aperture * 0.0001;
            bokeh.uniforms["maxblur"].value = 0.01;
          }
          composer.setSize(width, height);
          composer.render();
        } else if (outline) {
          // OutlineEffect leaves autoClear off between its passes; clear so frames never stack.
          renderer.setRenderTarget(null);
          renderer.clear(true, true, true);
          outline.autoClear = false;
          outline.render(scene, camera);
        } else {
          renderer.render(scene, camera);
        }
        return renderer.domElement;
      };
      // Screen position (0..1) of an object plus an optional 3D offset, for anchor3d layers.
      draw.project = (id, offset = [0, 0, 0]) => {
        const entry = objects.get(id);
        if (!entry) return null;
        const point = new Vector3(...offset).add(entry.node.position).project(camera);
        return [(point.x + 1) / 2, (1 - point.y) / 2, point.z < 1];
      };
      return draw;
    },
    dispose() {
      // Geometries, materials and textures can be shared by multiple GLB instances.
      const resources = new Set(Object.values(geometries));
      for (const {scene} of scenes.values()) {
        scene.traverse((node) => {
          if (node.shadow) resources.add(node.shadow);
          if (node.geometry) resources.add(node.geometry);
          const materials = Array.isArray(node.material) ? node.material : [node.material];
          for (const material of materials.filter(Boolean)) {
            resources.add(material);
            for (const value of Object.values(material)) {
              if (value?.isTexture) resources.add(value);
            }
          }
        });
      }
      resources.add(ramp);
      if (roomTexture) resources.add(roomTexture);
      for (const resource of resources) resource.dispose();
      pmrem.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
    },
  };
}
