import {readFileSync} from "node:fs";
import {Euler, Matrix3, Matrix4, Quaternion, Vector3} from "three";
import {OBB} from "three/addons/math/OBB.js";
import {lightingFor} from "./lighting.mjs";
import {objectTrack, poseAt, poseTrack} from "./pose.mjs";

const vector = (values) => new Vector3(...values);
const close = (a, b) => Math.abs(a - b) <= 0.00001;
const sameVector = (a, b) => a.every((value, index) => close(value, b[index]));

function box3d(hitbox, pose) {
  const turn = new Quaternion().setFromEuler(new Euler(...pose.rotation));
  const scale = vector(pose.scale);
  const transform = new Matrix4().compose(vector(pose.position), turn, scale);
  const rotation = new Matrix3().setFromMatrix4(new Matrix4().makeRotationFromQuaternion(turn));
  const center = vector(hitbox.center ?? [0, 0, 0]).applyMatrix4(transform);
  return new OBB(center, vector(hitbox.size).multiply(scale).multiplyScalar(0.5), rotation);
}

function box2d(layer, pose, width, height) {
  const [w, h] = layer.hitbox;
  const rotation = new Matrix3().setFromMatrix4(new Matrix4().makeRotationZ(-pose.rotate * Math.PI / 180));
  const scaleX = pose.scale_x ?? pose.scale;
  const scaleY = pose.scale_y ?? pose.scale;
  return new OBB(new Vector3(pose.x * width, pose.y * height, 0),
    new Vector3(w * width * scaleX / 2, h * height * scaleY / 2, 1), rotation);
}

function extent(box, axis) {
  const m = box.rotation.elements;
  return Math.abs(m[axis]) * box.halfSize.x + Math.abs(m[axis + 3]) * box.halfSize.y
    + Math.abs(m[axis + 6]) * box.halfSize.z;
}

function padded(box, padding) {
  const copy = box.clone();
  copy.halfSize.addScalar(padding).max(new Vector3(0.000001, 0.000001, 0.000001));
  return copy;
}

function overlap(a, b, margin) {
  return a && b && padded(a, -margin).intersectsOBB(padded(b, -margin));
}

function compile(shot, scenes) {
  if (!shot.three) return null;
  const spec = scenes[shot.three.scene];
  const camera = poseTrack({position: spec.camera.position, target: spec.camera.target}, shot.three.camera);
  const objects = new Map(spec.objects.map((obj) => [
    obj.id, {obj, track: objectTrack(obj, Object.hasOwn(shot.three.objects ?? {}, obj.id) ? shot.three.objects[obj.id] : [])},
  ]));
  return {spec, camera, objects, lastProgress: shot.end - shot.start > 1 ? 1 : 0};
}

function auditCut(rule, previous, current, issue) {
  if (rule.camera) {
    const a = poseAt(previous.camera, previous.lastProgress), b = poseAt(current.camera, 0);
    if (!sameVector(a.position, b.position) || !sameVector(a.target, b.target)
      || !close(previous.spec.camera.fov ?? 37, current.spec.camera.fov ?? 37)) {
      issue("cut_camera", [], "Camera framing changes across a locked cut");
    }
  }
  if (rule.lighting && JSON.stringify(lightingFor(previous.spec)) !== JSON.stringify(lightingFor(current.spec))) {
    issue("cut_lighting", [], "Lighting changes across a locked cut");
  }
  for (const id of rule.objects ?? []) {
    const a = previous.objects.get(id), b = current.objects.get(id);
    const end = poseAt(a.track, previous.lastProgress), start = poseAt(b.track, 0);
    if (a.obj.kind !== b.obj.kind || a.obj.file !== b.obj.file
      || (a.obj.color ?? "#ffffff").toLowerCase() !== (b.obj.color ?? "#ffffff").toLowerCase()
      || end.visible !== start.visible
      || !["position", "rotation", "scale"].every((key) => sameVector(end[key], start[key]))) {
      issue("cut_object", [id], "Object identity, visibility, or transform changes across a locked cut");
    }
  }
}

function audit({width, height, scenes, shots}) {
  const report = {checked_shots: 0, checked_frames: 0, issues: []};
  let previous;
  for (const shot of shots) {
    const current = compile(shot, scenes);
    if (shot.audit) {
      report.checked_shots++;
      const {checks} = shot;
      const count = shot.end - shot.start;
      const reported = new Set();
      let frame = shot.start;
      const issue = (kind, ids, message, key = JSON.stringify(ids)) => {
        const code = kind + ":" + key;
        if (reported.has(code)) return;
        reported.add(code);
        report.issues.push({shot: shot.id, frame, kind, ids, message});
      };
      if (checks.continuity) auditCut(checks.continuity, previous, current, issue);
      const contacts = (checks.contacts ?? []).map((rule) => ({...rule, frame: Math.round(rule.at * (count - 1))}));
      for (let offset = 0; offset < count; offset++) {
        frame = shot.start + offset;
        report.checked_frames++;
        const progress = offset / Math.max(1, count - 1);
        const flat = new Map();
        for (const layer of shot.layers) {
          const pose = poseAt(layer.poses, progress);
          if (pose.opacity > 0) flat.set(layer.id, box2d(layer, pose, width, height));
        }
        for (const pair of checks.avoid_2d ?? []) {
          if (overlap(...pair.map((id) => flat.get(id)), 0.5)) issue("overlap_2d", pair, "Protected 2D layers overlap");
        }
        for (const id of checks.keep_in_frame ?? []) {
          const box = flat.get(id);
          if (!box) continue;
          const x = extent(box, 0), y = extent(box, 1);
          if (box.center.x - x < -0.5 || box.center.x + x > width + 0.5
            || box.center.y - y < -0.5 || box.center.y + y > height + 0.5) {
            issue("frame_bounds", [id], "Protected layer extends outside the canvas");
          }
        }
        if (!current) continue;
        const camera = poseAt(current.camera, progress);
        if (sameVector(camera.position, camera.target)) issue("camera", [], "Camera position coincides with its target");

        const visible = new Map(), groups = new Map();
        for (const [id, {obj, track}] of current.objects) {
          const pose = poseAt(track, progress);
          if (!pose.visible) continue;
          if (obj.hitbox) visible.set(id, box3d(obj.hitbox, pose));
          if (obj.variant_group) {
            if (!groups.has(obj.variant_group)) groups.set(obj.variant_group, []);
            groups.get(obj.variant_group).push(id);
          }
        }
        for (const [group, ids] of groups) {
          if (ids.length > 1) issue("variant_overlap", ids, `Multiple visible variants in ${group}`, group);
        }
        for (const pair of checks.avoid_3d ?? []) {
          if (overlap(...pair.map((id) => visible.get(id)), 0.0005)) issue("collision", pair, "3D hitboxes penetrate");
        }
        if (checks.floor) {
          for (const id of checks.floor.objects) {
            const box = visible.get(id);
            if (box && box.center.y - extent(box, 1) < checks.floor.y - (checks.floor.tolerance ?? 0.01)) {
              issue("floor", [id], "Hitbox sinks below the floor plane");
            }
          }
        }
        for (const contact of contacts) {
          if (contact.frame !== offset) continue;
          const pair = contact.objects;
          const [a, b] = pair.map((id) => visible.get(id));
          const margin = (contact.tolerance ?? 0.02) / 2;
          const key = JSON.stringify([pair, offset]);
          if (!a || !b || !padded(a, margin).intersectsOBB(padded(b, margin))) {
            issue("missed_contact", pair, "Hitboxes miss their intended contact", key);
          } else if (overlap(a, b, Math.max(margin, 0.000001))) {
            issue("contact_penetration", pair, "Hitboxes penetrate at the intended contact", key);
          }
        }
      }
    }
    previous = current;
  }
  return report;
}

const plan = JSON.parse(readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(audit(plan)));
