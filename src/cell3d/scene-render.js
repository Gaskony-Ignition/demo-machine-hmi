// Build a three.js scene graph from a scene document.
//
// This is the Option A renderer: the cell's parts list becomes data, and this
// walks it. It is deliberately a plain script that defines one global,
// buildScene(), so it can be pasted into page.html, loaded on its own by the
// parity harness, or lifted into a Perspective component later without an
// import system in the way.
//
// It knows nothing about this demo. Everything specific to the palletising
// cell lives in scene.json.
(function (global) {
  "use strict";

  // --------------------------------------------------------------------
  // Expressions. A prefix array, walked - no eval, so a scene document can
  // come off a tag or a prop without being a code-execution surface.
  // --------------------------------------------------------------------
  var OPS = {
    "+": function (a) { return a.reduce(function (x, y) { return x + y; }, 0); },
    "*": function (a) { return a.reduce(function (x, y) { return x * y; }, 1); },
    "-": function (a) { return a.length === 1 ? -a[0] : a.slice(1).reduce(function (x, y) { return x - y; }, a[0]); },
    "/": function (a) { return a.slice(1).reduce(function (x, y) { return x / y; }, a[0]); },
    "neg": function (a) { return -a[0]; },
    "abs": function (a) { return Math.abs(a[0]); },
    "min": function (a) { return Math.min.apply(Math, a); },
    "max": function (a) { return Math.max.apply(Math, a); },
    "floor": function (a) { return Math.floor(a[0]); },
    "ceil": function (a) { return Math.ceil(a[0]); },
    "round": function (a) { return Math.round(a[0]); },
    "sqrt": function (a) { return Math.sqrt(a[0]); },
    "atan2": function (a) { return Math.atan2(a[0], a[1]); },
    "hypot": function (a) { return Math.sqrt(a.reduce(function (s, v) { return s + v * v; }, 0)); }
  };

  function SceneError(msg) {
    var e = new Error("scene: " + msg);
    e.name = "SceneError";
    return e;
  }

  // A name resolves against the scope chain, then consts, then config. A
  // config path ending _mm is millimetres and the page works in metres, so it
  // is divided here rather than in every part that mentions one.
  function lookup(name, ctx) {
    var dot = name.indexOf(".");
    if (dot > 0) {
      var row = lookup(name.slice(0, dot), ctx);
      var field = name.slice(dot + 1);
      if (row === null || typeof row !== "object" || !(field in row)) {
        throw SceneError('"' + name + '" - no field "' + field + '" on that row');
      }
      // A row's fields may themselves be expressions, evaluated in the scope
      // the repeat runs in - so a table of photo-eye positions can be written
      // as distances back from the end of a conveyor whose length is a tag.
      var val = row[field];
      return typeof val === "number" ? val : evaluate(val, ctx);
    }
    for (var i = ctx.scope.length - 1; i >= 0; i--) {
      if (Object.prototype.hasOwnProperty.call(ctx.scope[i], name)) return ctx.scope[i][name];
    }
    if (Object.prototype.hasOwnProperty.call(ctx.consts, name)) return ctx.consts[name];
    if (name.indexOf("Config/") === 0) {
      var key = name.slice(7);
      if (!Object.prototype.hasOwnProperty.call(ctx.config, key)) {
        throw SceneError('"' + name + '" - not in the config');
      }
      var v = ctx.config[key];
      return /_mm$/.test(key) ? v / 1000 : v;
    }
    throw SceneError('"' + name + '" is not a const, a loop variable or a Config path');
  }

  function evaluate(node, ctx) {
    if (typeof node === "number") return node;
    if (typeof node === "string") {
      var v = lookup(node, ctx);
      if (typeof v !== "number") throw SceneError('"' + node + '" is not a number');
      return v;
    }
    if (Array.isArray(node)) {
      var op = OPS[node[0]];
      if (!op) throw SceneError('unknown operator "' + node[0] + '"');
      var args = [];
      for (var i = 1; i < node.length; i++) args.push(evaluate(node[i], ctx));
      return op(args);
    }
    throw SceneError("cannot evaluate " + JSON.stringify(node));
  }

  function vec(node, ctx, len, what) {
    if (!Array.isArray(node)) throw SceneError(what + " must be an array of " + len);
    if (node.length !== len) throw SceneError(what + " needs " + len + " values, got " + node.length);
    return node.map(function (n) { return evaluate(n, ctx); });
  }

  // --------------------------------------------------------------------
  // Materials
  // --------------------------------------------------------------------
  function buildMaterials(defs, THREE) {
    var out = {};
    Object.keys(defs || {}).forEach(function (name) {
      var d = defs[name];
      var opts = {
        color: typeof d.color === "string" ? parseInt(d.color, 16) : d.color,
        metalness: d.metalness !== undefined ? d.metalness : 0.55,
        roughness: d.roughness !== undefined ? d.roughness : 0.55
      };
      if (d.opacity !== undefined) { opts.transparent = true; opts.opacity = d.opacity; }
      if (d.side === "double") opts.side = THREE.DoubleSide;
      if (d.depthWrite === false) opts.depthWrite = false;
      out[name] = d.basic ? new THREE.MeshBasicMaterial(opts)
                          : new THREE.MeshStandardMaterial(opts);
    });
    return out;
  }

  // --------------------------------------------------------------------
  // Parts
  // --------------------------------------------------------------------
  function makeObject(part, ctx, THREE) {
    var mat = null;
    if (part.material) {
      mat = ctx.materials[part.material];
      if (!mat) throw SceneError('part "' + part.name + '" wants material "' + part.material + '", which is not defined');
      // Materials are shared by name, which is what you want for sixty
      // identical cartons and exactly what you do not want for six photo-eye
      // beams: each beam's colour is its own tag, and one shared material
      // would turn them all red together. `ownMaterial` gives each instance
      // its own copy - the same reason the page clones materials before it
      // highlights a faulted group.
      if (part.ownMaterial) mat = mat.clone();
    }
    var o;
    switch (part.type) {
      case "group":
        o = new THREE.Group();
        break;
      case "box":
        var s = vec(part.size, ctx, 3, '"' + part.name + '".size');
        o = new THREE.Mesh(new THREE.BoxGeometry(s[0], s[1], s[2]), mat);
        break;
      case "plane":
        var p = vec(part.size, ctx, 2, '"' + part.name + '".size');
        o = new THREE.Mesh(new THREE.PlaneGeometry(p[0], p[1]), mat);
        break;
      case "cylinder":
        o = new THREE.Mesh(new THREE.CylinderGeometry(
          evaluate(part.radiusTop, ctx), evaluate(part.radiusBottom, ctx),
          evaluate(part.height, ctx), part.segments || 20), mat);
        break;
      default:
        throw SceneError('part "' + part.name + '" has unknown type "' + part.type + '"');
    }

    if (part.at) { var a = vec(part.at, ctx, 3, '"' + part.name + '".at'); o.position.set(a[0], a[1], a[2]); }
    if (part.rotate) { var r = vec(part.rotate, ctx, 3, '"' + part.name + '".rotate'); o.rotation.set(r[0], r[1], r[2]); }
    if (part.visible === false) o.visible = false;

    if (o.isMesh) {
      var sh = part.shadow || {};
      o.castShadow = sh.cast !== false;
      o.receiveShadow = sh.receive !== false;
    }
    return o;
  }

  // How many times a part runs, and what each iteration binds.
  //
  // `repeat` may be an array, innermost last, which produces the cartesian
  // product of the bindings - a pallet's rows by columns, or a conveyor's leg
  // positions by side. Nesting groups to get the same effect would put phantom
  // transforms in the tree that the machine does not have.
  function iterations(part, ctx) {
    var rep = part.repeat;
    if (!rep) return [null];
    if (Array.isArray(rep)) {
      var acc = [{}];
      for (var r = 0; r < rep.length; r++) {
        var next = [];
        for (var a = 0; a < acc.length; a++) {
          // Outer bindings must be visible while an inner count is evaluated.
          ctx.scope.push(acc[a]);
          var inner = oneRepeat(rep[r], part, ctx);
          ctx.scope.pop();
          for (var b = 0; b < inner.length; b++) {
            var merged = {};
            Object.keys(acc[a]).forEach(function (k) { merged[k] = acc[a][k]; });
            Object.keys(inner[b]).forEach(function (k) { merged[k] = inner[b][k]; });
            next.push(merged);
          }
        }
        acc = next;
      }
      return acc;
    }
    return oneRepeat(rep, part, ctx);
  }

  function oneRepeat(rep, part, ctx) {
    if (rep.over) {
      var rows = ctx.data[rep.over];
      if (!Array.isArray(rows)) throw SceneError('part "' + part.name + '" repeats over "' + rep.over + '", which is not a table in `data`');
      return rows.map(function (row, i) { var b = {}; b[rep.as] = row; b[rep.as + "_i"] = i; return b; });
    }
    var n = evaluate(rep.count, ctx);
    if (!(n >= 0) || Math.floor(n) !== n) throw SceneError('part "' + part.name + '" repeat count is ' + n + ', which is not a whole number >= 0');
    var out = [];
    for (var i = 0; i < n; i++) { var bind = {}; bind[rep.as] = i; out.push(bind); }
    return out;
  }

  function buildPart(part, parentObj, ctx, THREE, sink) {
    var reps = iterations(part, ctx);
    for (var k = 0; k < reps.length; k++) {
      ctx.scope.push(reps[k] || {});

      // `let` names are evaluated in order, each visible to the next.
      var lets = {};
      if (part["let"]) {
        ctx.scope.push(lets);
        Object.keys(part["let"]).forEach(function (name) {
          lets[name] = evaluate(part["let"][name], ctx);
        });
      }

      var obj;
      try {
        obj = makeObject(part, ctx, THREE);
      } catch (e) {
        if (e.name === "SceneError") throw SceneError('in part "' + part.name + '": ' + e.message.replace(/^scene: /, ""));
        throw e;
      }
      // A repeated part is normally name.0, name.1 ... but a row may carry the
      // name it should have. The two pallet stations are Station1 and Station2
      // everywhere else in this project - in the tags, in the state route and
      // in the simulator - and a scene document that called them Station.0 and
      // Station.1 would have renamed the machine to suit the renderer.
      var repSpec = Array.isArray(part.repeat) ? null : part.repeat;
      var explicit = null;
      if (repSpec && repSpec.nameFrom && reps[k]) {
        var row = reps[k][repSpec.as];
        if (row === null || typeof row !== "object" || !(repSpec.nameFrom in row)) {
          throw SceneError('part "' + part.name + '" names instances from "' + repSpec.nameFrom + '", which that row does not have');
        }
        explicit = String(row[repSpec.nameFrom]);
      }
      obj.name = explicit || (reps[k] ? part.name + "." + k : part.name);

      if (part.joint) {
        var j = part.joint;
        obj.userData.joint = {
          kind: j.kind === "translate" ? "translate" : "rotate",
          axis: j.axis, tag: j.tag,
          unit: j.unit || (j.kind === "translate" ? "mm" : "deg")
        };
        sink.joints.push({ name: obj.name, object: obj, joint: obj.userData.joint });
      }

      parentObj.add(obj);
      sink.byName[obj.name] = obj;

      // Children repeat with their parent, seeing its loop variable and lets.
      var kids = ctx.childrenOf[part.name] || [];
      for (var c = 0; c < kids.length; c++) buildPart(kids[c], obj, ctx, THREE, sink);

      if (part["let"]) ctx.scope.pop();
      ctx.scope.pop();
    }
  }

  // --------------------------------------------------------------------
  // Entry point
  // --------------------------------------------------------------------
  // doc     - the scene document
  // config  - the flat config bag the page already builds from Config tags
  // THREE   - the three.js namespace
  // returns { root, byName, joints, materials }
  function buildScene(doc, config, THREE) {
    if (!doc || !Array.isArray(doc.parts)) throw SceneError("document has no `parts` array");

    var ctx = {
      consts: doc.consts || {},
      data: doc.data || {},
      config: config || {},
      materials: buildMaterials(doc.materials, THREE),
      scope: [],
      childrenOf: {}
    };

    var seen = {};
    doc.parts.forEach(function (p) {
      if (!p.name) throw SceneError("every part needs a name");
      if (seen[p.name]) throw SceneError('two parts are called "' + p.name + '"');
      seen[p.name] = true;
    });
    doc.parts.forEach(function (p) {
      if (!p.parent) return;
      if (!seen[p.parent]) throw SceneError('part "' + p.name + '" names parent "' + p.parent + '", which does not exist');
      (ctx.childrenOf[p.parent] = ctx.childrenOf[p.parent] || []).push(p);
    });

    var root = new THREE.Group();
    root.name = "SceneRoot";
    var sink = { byName: {}, joints: [] };
    doc.parts.filter(function (p) { return !p.parent; })
             .forEach(function (p) { buildPart(p, root, ctx, THREE, sink); });

    return { root: root, byName: sink.byName, joints: sink.joints, materials: ctx.materials };
  }

  // Drive the joints from a state bag: { "Robot/J1_deg": 12.5, ... }
  function applyJoints(built, values) {
    built.joints.forEach(function (j) {
      var v = values[j.joint.tag];
      if (typeof v !== "number") return;
      if (j.joint.kind === "translate") {
        j.object.position[j.joint.axis] = j.joint.unit === "mm" ? v / 1000 : v;
      } else {
        j.object.rotation[j.joint.axis] = j.joint.unit === "rad" ? v : v * Math.PI / 180;
      }
    });
  }

  global.buildScene = buildScene;
  global.applyJoints = applyJoints;
})(typeof window !== "undefined" ? window : globalThis);
