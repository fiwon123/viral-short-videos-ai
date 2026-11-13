import {
  ACESFilmicToneMapping, AmbientLight, AnimationMixer, BoxGeometry, Color, CylinderGeometry,
  DirectionalLight, Mesh, MeshStandardMaterial, PCFShadowMap, PerspectiveCamera, Scene,
  SphereGeometry, SRGBColorSpace, TorusGeometry, WebGLRenderer,
} from "three";
import {GLTFLoader} from "three/addons/loaders/GLTFLoader.js";
import {clone} from "three/addons/utils/SkeletonUtils.js";
import {EffectComposer} from "three/addons/postprocessing/EffectComposer.js";
import {RenderPass} from "three/addons/postprocessing/RenderPass.js";
import {BokehPass} from "three/addons/postprocessing/BokehPass.js";

import {lightingFor} from "./lighting.mjs";
import {objectTrack, poseAt, poseTrack} from "./pose.mjs";

export async function createThreeStage(specs, width, height, urlFor) {
  const renderer = new WebGLRenderer({alpha: true, antialias: true});
  renderer.setSize(width, height, false);
  renderer.setClearColor(0, 0);
  renderer.toneMapping = ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.outputColorSpace = SRGBColorSpace;
  renderer.shadowMap.enabled = Object.values(specs).some((spec) => spec.lighting?.shadows);
  renderer.shadowMap.type = PCFShadowMap;
  const geometries = {
    box: new BoxGeometry(1, 1, 1),
    sphere: new SphereGeometry(0.5, 36, 24),
    cylinder: new CylinderGeometry(0.5, 0.5, 1, 48),
    torus: new TorusGeometry(0.38, 0.12, 16, 48),
  };
  const loader = new GLTFLoader();
  const models = new Map();
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
        key.shadow.mapSize.set(1024, 1024);
        Object.assign(key.shadow.camera, {
          left: -extent, right: extent, top: extent, bottom: -extent,
          near: 0.01, far: key.position.distanceTo(key.target.position) + extent * 3,
        });
        key.shadow.camera.updateProjectionMatrix();
        key.shadow.normalBias = 0.015;
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
        } else {
          node = new Mesh(geometries[obj.kind], new MeshStandardMaterial({
            color: obj.color ?? "#ffffff",
            metalness: obj.metalness ?? 0,
            roughness: obj.roughness ?? 0.62,
            emissive: new Color(obj.emissive ?? "#000000"),
            emissiveIntensity: obj.emissive_intensity ?? 1,
          }));
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
      scenes.set(id, {scene, camera, initialCamera: {
        position: spec.camera.position, target: spec.camera.target,
        fov: spec.camera.fov ?? 37,
      }, objects});
    }
  } catch (error) {
    renderer.dispose();
    throw error;
  }

  return {
    compile(shot) {
      const {scene, camera, initialCamera, objects} = scenes.get(shot.scene);
      const cameraTrack = poseTrack(initialCamera, shot.camera);
      const duration = shot.duration ?? 1;
      const focusTrack = shot.focus?.length
        ? poseTrack({distance: 2, aperture: 1}, shot.focus) : null;
      let composer = null;
      let bokeh = null;
      if (focusTrack) {
        composer = new EffectComposer(renderer);
        composer.addPass(new RenderPass(scene, camera));
        bokeh = new BokehPass(scene, camera, {focus: 2, aperture: 0.0001, maxblur: 0.01});
        composer.addPass(bokeh);
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
        return {
          node,
          poses: objectTrack(spec, Object.hasOwn(shot.objects ?? {}, id) ? shot.objects[id] : []),
          mixer: actions.length ? mixer : null,
          actions,
        };
      });
      return (progress) => {
        const {position, target, fov} = poseAt(cameraTrack, progress);
        camera.position.set(...position);
        camera.lookAt(...target);
        if (fov !== undefined && camera.fov !== fov) {
          camera.fov = fov;
          camera.updateProjectionMatrix();
        }
        for (const {node, poses, mixer, actions} of tracks) {
          const pose = poseAt(poses, progress);
          node.visible = pose.visible;
          node.position.set(...pose.position);
          node.rotation.set(...pose.rotation);
          node.scale.set(...pose.scale);
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
        }
        if (composer && bokeh) {
          const focus = poseAt(focusTrack, progress);
          bokeh.uniforms["focus"].value = focus.distance;
          bokeh.uniforms["aperture"].value = focus.aperture * 0.0001;
          bokeh.uniforms["maxblur"].value = 0.01;
          composer.setSize(width, height);
          composer.render();
        } else {
          renderer.render(scene, camera);
        }
        return renderer.domElement;
      };
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
      for (const resource of resources) resource.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
    },
  };
}
