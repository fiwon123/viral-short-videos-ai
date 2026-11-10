import {
  AmbientLight, BoxGeometry, CylinderGeometry, DirectionalLight, Mesh, MeshStandardMaterial,
  PerspectiveCamera, Scene, SphereGeometry, TorusGeometry, WebGLRenderer,
} from "three";
import {GLTFLoader} from "three/addons/loaders/GLTFLoader.js";
import {clone} from "three/addons/utils/SkeletonUtils.js";

import {poseAt, poseTrack} from "./pose.mjs";

export async function createThreeStage(specs, width, height, urlFor) {
  const renderer = new WebGLRenderer({alpha: true, antialias: true});
  renderer.setSize(width, height, false);
  renderer.setClearColor(0, 0);
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
      const light = spec.lighting ?? {};
      const key = new DirectionalLight(light.color ?? "#ffffff", light.key ?? 2.8);
      key.position.set(...(light.position ?? [-3, 6, 5]));
      scene.add(new AmbientLight("#ffffff", light.ambient ?? 1.05), key);
      const camera = new PerspectiveCamera(spec.camera.fov ?? 37, width / height, 0.01, 2000);
      const objects = new Map();
      for (const obj of spec.objects) {
        let node;
        if (obj.kind === "glb") {
          if (!models.has(obj.file)) models.set(obj.file, await loader.loadAsync(urlFor(obj.file)));
          node = clone(models.get(obj.file).scene);
        } else {
          node = new Mesh(geometries[obj.kind], new MeshStandardMaterial({color: obj.color ?? "#ffffff"}));
        }
        scene.add(node);
        objects.set(obj.id, {node, initial: {
          position: obj.position, rotation: obj.rotation ?? [0, 0, 0], scale: obj.scale ?? [1, 1, 1],
        }});
      }
      scenes.set(id, {scene, camera, initialCamera: {
        position: spec.camera.position, target: spec.camera.target,
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
      const tracks = Array.from(objects, ([id, {node, initial}]) => ({
        node, poses: poseTrack(initial, Object.hasOwn(shot.objects ?? {}, id) ? shot.objects[id] : []),
      }));
      return (progress) => {
        const {position, target} = poseAt(cameraTrack, progress);
        camera.position.set(...position);
        camera.lookAt(...target);
        for (const {node, poses} of tracks) {
          const pose = poseAt(poses, progress);
          node.position.set(...pose.position);
          node.rotation.set(...pose.rotation);
          node.scale.set(...pose.scale);
        }
        renderer.render(scene, camera);
        return renderer.domElement;
      };
    },
    dispose() {
      // Geometries, materials and textures can be shared by multiple GLB instances.
      const resources = new Set(Object.values(geometries));
      for (const {scene} of scenes.values()) {
        scene.traverse((node) => {
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
