import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';

export default function CacheCluster3D({ backend = 'memory', health = 'healthy', stats = {} }) {
  const containerRef = useRef(null);
  const [isInteractive, setIsInteractive] = useState(true);
  const [cameraDistance, setCameraDistance] = useState(14);
  const sceneRef = useRef(null);
  const rendererRef = useRef(null);
  const centralMeshRef = useRef(null);
  const ringsRef = useRef([]);
  const satellitesRef = useRef([]);
  const particlesRef = useRef(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Dimensions
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 340;

    // 1. Scene
    const scene = new THREE.Scene();
    sceneRef.current = scene;

    // 2. Camera
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(0, 3, cameraDistance);
    camera.lookAt(0, 0, 0);

    // 3. Renderer with antialias and alpha (gracefully fallback if WebGL not present)
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.shadowMap.enabled = true;
      container.innerHTML = '';
      container.appendChild(renderer.domElement);
      rendererRef.current = renderer;
    } catch (err) {
      // WebGL not available (e.g. headless jsdom test runner)
      return;
    }


    // 4. Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const pointLight = new THREE.PointLight(
      backend === 'redis' ? 0xf43f5e : backend === 'memcached' ? 0x06b6d4 : 0x10b981,
      4,
      50
    );
    pointLight.position.set(5, 8, 8);
    scene.add(pointLight);

    const backLight = new THREE.PointLight(0x6366f1, 2, 40);
    backLight.position.set(-6, -4, -6);
    scene.add(backLight);

    // 5. Central Node (geometry depends on active backend)
    let centralGeo;
    let centralColor;
    let wireColor;

    if (backend === 'redis') {
      centralGeo = new THREE.DodecahedronGeometry(2.2, 0);
      centralColor = 0xf43f5e;
      wireColor = 0xfb7185;
    } else if (backend === 'memcached') {
      centralGeo = new THREE.OctahedronGeometry(2.4, 0);
      centralColor = 0x06b6d4;
      wireColor = 0x38bdf8;
    } else {
      centralGeo = new THREE.IcosahedronGeometry(2.2, 0);
      centralColor = 0x10b981;
      wireColor = 0x34d399;
    }

    // Core solid mesh
    const centralMat = new THREE.MeshStandardMaterial({
      color: centralColor,
      roughness: 0.2,
      metalness: 0.8,
      emissive: centralColor,
      emissiveIntensity: 0.25,
      transparent: true,
      opacity: 0.9,
    });
    const centralMesh = new THREE.Mesh(centralGeo, centralMat);
    scene.add(centralMesh);
    centralMeshRef.current = centralMesh;

    // Core wireframe overlay for high-tech holographic depth
    const wireGeo = new THREE.WireframeGeometry(centralGeo);
    const wireMat = new THREE.LineBasicMaterial({ color: wireColor, linewidth: 2, transparent: true, opacity: 0.85 });
    const wireMesh = new THREE.LineSegments(wireGeo, wireMat);
    centralMesh.add(wireMesh);

    // 6. Orbital Rings
    ringsRef.current = [];
    const ringColors = [0x6366f1, centralColor, 0xa855f7];
    const ringRadii = [3.6, 4.4, 5.2];

    ringRadii.forEach((rad, idx) => {
      const ringGeo = new THREE.TorusGeometry(rad, 0.04, 16, 100);
      const ringMat = new THREE.MeshBasicMaterial({
        color: ringColors[idx % ringColors.length],
        transparent: true,
        opacity: 0.5,
      });
      const ringMesh = new THREE.Mesh(ringGeo, ringMat);
      ringMesh.rotation.x = Math.PI / (2 + idx * 0.4);
      ringMesh.rotation.y = (Math.PI / 4) * idx;
      scene.add(ringMesh);
      ringsRef.current.push(ringMesh);
    });

    // 7. Satellites (Cache Cluster Shards / Nodes)
    satellitesRef.current = [];
    const numSatellites = 6;
    for (let i = 0; i < numSatellites; i++) {
      const satGeo = new THREE.SphereGeometry(0.35, 16, 16);
      const satMat = new THREE.MeshStandardMaterial({
        color: 0xffffff,
        emissive: centralColor,
        emissiveIntensity: 0.6,
        roughness: 0.1,
      });
      const satMesh = new THREE.Mesh(satGeo, satMat);
      scene.add(satMesh);
      satellitesRef.current.push({
        mesh: satMesh,
        angle: (i / numSatellites) * Math.PI * 2,
        speed: 0.015 + (i % 3) * 0.005,
        radius: 4.6 + (i % 2) * 1.2,
        heightOffset: Math.sin(i) * 1.5,
      });
    }

    // 8. Dynamic Data Particles (floating memory constellation)
    const particleCount = 180;
    const particleGeo = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);

    for (let i = 0; i < particleCount * 3; i += 3) {
      positions[i] = (Math.random() - 0.5) * 22;
      positions[i + 1] = (Math.random() - 0.5) * 16;
      positions[i + 2] = (Math.random() - 0.5) * 20;
    }
    particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const particleMat = new THREE.PointsMaterial({
      color: 0xc7d2fe,
      size: 0.12,
      transparent: true,
      opacity: 0.6,
    });
    const particles = new THREE.Points(particleGeo, particleMat);
    scene.add(particles);
    particlesRef.current = particles;

    // 9. Interactive mouse rotation & parallax
    let mouseX = 0;
    let mouseY = 0;
    let isDragging = false;
    let previousMouseX = 0;
    let previousMouseY = 0;

    const onMouseMove = (e) => {
      const rect = container.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width - 0.5;
      const y = (e.clientY - rect.top) / rect.height - 0.5;

      if (isDragging) {
        const deltaX = e.clientX - previousMouseX;
        const deltaY = e.clientY - previousMouseY;
        centralMesh.rotation.y += deltaX * 0.01;
        centralMesh.rotation.x += deltaY * 0.01;
      } else {
        mouseX = x;
        mouseY = y;
      }
      previousMouseX = e.clientX;
      previousMouseY = e.clientY;
    };

    const onMouseDown = (e) => {
      isDragging = true;
      previousMouseX = e.clientX;
      previousMouseY = e.clientY;
    };

    const onMouseUp = () => {
      isDragging = false;
    };

    container.addEventListener('mousemove', onMouseMove);
    container.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mouseup', onMouseUp);

    // 10. Animation Loop
    let animationFrameId;
    let clock = new THREE.Clock();

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      const elapsedTime = clock.getElapsedTime();

      // Central core breathing & smooth spin
      if (centralMeshRef.current) {
        if (!isDragging) {
          centralMeshRef.current.rotation.y += 0.008;
          centralMeshRef.current.rotation.x = Math.sin(elapsedTime * 0.8) * 0.15 + mouseY * 0.8;
          centralMeshRef.current.position.y = Math.sin(elapsedTime * 1.5) * 0.2;
        }
        // Subtle pulse scale
        const pulse = 1 + Math.sin(elapsedTime * 2.5) * 0.03;
        centralMeshRef.current.scale.set(pulse, pulse, pulse);
      }

      // Orbital rings rotation
      ringsRef.current.forEach((ring, idx) => {
        ring.rotation.z += (idx % 2 === 0 ? 0.01 : -0.012);
        ring.rotation.x += 0.004;
      });

      // Satellites orbiting
      satellitesRef.current.forEach((sat) => {
        sat.angle += sat.speed;
        sat.mesh.position.x = Math.cos(sat.angle) * sat.radius;
        sat.mesh.position.z = Math.sin(sat.angle) * sat.radius;
        sat.mesh.position.y = sat.heightOffset + Math.sin(sat.angle * 2) * 0.6;
      });

      // Ambient particle cloud slow drift
      if (particlesRef.current) {
        particlesRef.current.rotation.y = elapsedTime * 0.02;
        particlesRef.current.rotation.x = mouseX * 0.2;
      }

      // Smooth camera dampening to mouse
      if (!isDragging) {
        camera.position.x += (mouseX * 4 - camera.position.x) * 0.05;
        camera.position.y += (-mouseY * 3 + 2.5 - camera.position.y) * 0.05;
        camera.lookAt(0, 0, 0);
      }

      renderer.render(scene, camera);
    };

    animate();

    // Resize Handler
    const handleResize = () => {
      if (!container) return;
      const newW = container.clientWidth;
      const newH = container.clientHeight;
      camera.aspect = newW / newH;
      camera.updateProjectionMatrix();
      renderer.setSize(newW, newH);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', handleResize);
      container.removeEventListener('mousemove', onMouseMove);
      container.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mouseup', onMouseUp);
      if (renderer.domElement && container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
      renderer.dispose();
    };
  }, [backend, cameraDistance]);

  return (
    <div className="three-cluster-container" id="three-cluster-container">
      {/* Three.js canvas container */}
      <div 
        ref={containerRef} 
        id="three-canvas-viewport" 
        style={{ width: '100%', height: '300px', cursor: 'grab' }}
      />

      {/* 3D Holographic HUD overlay */}
      <div className="three-hud-overlay">
        <div className="three-hud-badge">
          <span className="three-hud-dot" style={{
            background: backend === 'redis' ? 'var(--accent-rose)' : backend === 'memcached' ? 'var(--accent-cyan)' : 'var(--accent-emerald)'
          }}></span>
          <span>3D LIVE CORE &bull; <strong style={{ textTransform: 'uppercase' }}>{backend}</strong></span>
        </div>

        <div className="three-hud-stats">
          <div><span className="three-hud-label">GEOMETRY:</span> <span className="three-hud-val">{backend === 'redis' ? 'Dodecahedron' : backend === 'memcached' ? 'Octahedron' : 'Icosahedron'}</span></div>
          <div><span className="three-hud-label">SHARDS:</span> <span className="three-hud-val">6 Nodes</span></div>
          <div><span className="three-hud-label">STATUS:</span> <span className="three-hud-val" style={{ color: health === 'healthy' ? '#10b981' : '#f43f5e' }}>{health}</span></div>
          <div><span className="three-hud-label">INTERACTION:</span> <span className="three-hud-val">Drag to rotate</span></div>
        </div>
      </div>
    </div>
  );
}
