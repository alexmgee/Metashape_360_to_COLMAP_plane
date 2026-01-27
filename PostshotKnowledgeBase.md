# **The Volumetric Paradigm: A Technical Analysis of Jawset Postshot and the Democratization of Radiance Fields**

## **1\. Introduction: The Evolution of Digital Reconstruction**

The history of computer graphics has been a relentless pursuit of simulating reality, a journey that has transitioned from the rigid, polygon-based geometry of the 1990s to the physically based rendering (PBR) of the 2010s. However, the last half-decade has witnessed a paradigm shift arguably more significant than the introduction of programmable shaders: the emergence of Neural Radiance Fields (NeRFs) and subsequently, 3D Gaussian Splatting (3DGS). These technologies have moved the industry from explicitly modeling light transport on surfaces to implicitly learning the light field of a volume.  
Within this rapidly evolving landscape, **Jawset Postshot** has emerged as a critical bridge between the bleeding-edge, code-heavy academic research of neural rendering and the stable, pipeline-driven requirements of professional visual effects (VFX). Developed by **Jawset Visual Computing**, a German software house founded by **Jascha Wetzel**, Postshot is not merely a graphical user interface for open-source libraries; it is a proprietary, highly optimized engine that leverages decades of experience in volumetric fluid simulation.1  
This report provides an exhaustive, technical deep-dive into the architecture, algorithmic underpinnings, and production utility of Postshot. By dissecting its development trajectory—from the fluid dynamics of **TurbulenceFD** to the probabilistic rendering of **Markov Chain Monte Carlo (MCMC)** splats—we reveal a piece of software designed to fundamentally alter how digital twins, virtual production assets, and volumetric video are created and integrated.

### **1.1 The Lineage of Volumetrics: From Fluid to Field**

To understand the engineering philosophy behind Postshot, one must first examine the pedigree of its developer. Jascha Wetzel and Jawset Visual Computing rose to prominence in the early 2010s with the release of **TurbulenceFD (TFD)**.2 TFD was a pioneering plugin for Cinema 4D and LightWave that brought voxel-based gaseous fluid simulation (smoke, fire, explosions) to the masses.  
The technical challenges inherent in fluid simulation are strikingly similar to those in 3D Gaussian Splatting:

1. **Sparse Data Structures:** Both fluids and radiance fields represent volumetric data that is mostly empty space. Efficiently storing and accessing the "active" regions (whether smoke density or Gaussian opacity) without wasting memory on empty air is a core optimization problem.2  
2. **GPU Acceleration:** TFD was among the first tools to implement hybrid CPU/GPU solvers, offloading massive parallel computations (advection, diffusion) to CUDA cores while managing memory transfer bottlenecks.  
3. **VRAM Management:** High-resolution simulations, like high-fidelity splats, easily exceed the VRAM capacity of consumer GPUs. Techniques for "paging" data or utilizing compact workspaces are critical.

Postshot can be viewed as the application of these specific high-performance computing (HPC) competencies to the domain of photogrammetry. While traditional photogrammetry (Structure-from-Motion followed by Multi-View Stereo) reconstructs a *surface* (mesh), Postshot reconstructs a *field*. The transition from managing voxels in TFD to managing Gaussian primitives in Postshot is a logical evolution of Jawset’s core IP: the efficient manipulation of massive, sparse volumetric datasets on NVIDIA hardware.3

### **1.2 The Local Processing Philosophy**

A defining characteristic of Postshot is its adherence to a strictly local processing model. In an era where competitors like Luma AI, Polycam, and KIRI Engine emphasize cloud-based "black box" processing, Postshot is architected for the on-premise workstation.3 This design choice is not merely a preference but a requirement for high-end production environments, driven by three factors:

1. **Data Sovereignty and Security:** Major film studios, automotive manufacturers, and defense contractors operate under strict Non-Disclosure Agreements (NDAs) and security protocols (e.g., TPN \- Trusted Partner Network). Uploading unreleased assets or sensitive site scans to a third-party cloud server is often contractually prohibited. Postshot allows these entities to keep the entire pipeline—from ingestion to training to rendering—completely offline.4  
2. **Iteration Speed:** Cloud processing introduces latency. Uploading gigabytes of 8K EXR sequences, waiting in a server queue, and downloading the result precludes rapid iteration. Local processing on an RTX 4090 allows for "live" training previews, where an artist can identify issues (e.g., poor camera coverage) within minutes and adjust parameters on the fly.5  
3. **Hardware Utilization:** The software is explicitly optimized for NVIDIA GPUs with Compute Capability 7.5 or higher (RTX 2060 and up). By writing close-to-metal CUDA code, Postshot extracts maximum performance from the Tensor Cores and RT Cores available on modern workstations, performance that is diluted in virtualized cloud instances.3

## ---

**2\. The Theoretical Framework: 3D Gaussian Splatting**

Before dissecting Postshot's specific implementation, it is necessary to establish the theoretical framework of the technology it harnesses. **3D Gaussian Splatting (3DGS)**, introduced by Kerbl et al. (Inria) in 2023, represents a departure from the implicit neural representations of NeRFs.

### **2.1 The Limitations of NeRF**

Early versions of Postshot (prior to v0.5) supported NeRF profiles. NeRFs encode a scene into the weights of a Multi-Layer Perceptron (MLP). To render a pixel, the engine shoots a ray into the scene, samples hundreds of points along that ray, feeds those coordinates into the neural network, and integrates the output (color and density).

* **The Bottleneck:** This requires millions of neural network evaluations per frame. While quality is high, training is slow (hours), and rendering is computationally expensive, often requiring powerful GPUs just to achieve low frame rates.  
* **The Editability Problem:** A neural network is a "black box." You cannot easily delete a specific object (e.g., a unwanted person) from a NeRF because that object exists as distributed weights across the entire network.6

### **2.2 The Gaussian Solution**

3DGS replaces the neural network with an explicit list of geometric primitives: **3D Gaussians**. Each Gaussian is an anisotropic (ellipsoidal) blob defined by:

1. **Position (Mean):** XYZ coordinates.  
2. **Covariance:** Defining the spread and rotation (scale and quaternion).  
3. **Opacity:** How transparent the blob is.  
4. **Color:** Spherical Harmonics (SH) coefficients that change color based on viewing angle.7

Rendering is performed via **Rasterization**, not ray-marching. The Gaussians are sorted by depth and "splatted" onto the screen, similar to how polygons are rasterized but with alpha blending. This allows for:

* **Real-time performance:** 100+ FPS on consumer hardware.  
* **Explicit Editability:** Since the scene is just a list of points (saved as a PLY file), users can delete, move, or color-correct specific points.4

Postshot’s adoption of 3DGS and removal of NeRF profiles in December 2024 6 signifies the industry’s standardization on Splatting as the superior format for visual effects, where editability and render speed are paramount.

## ---

**3\. Architecture of Ingestion and Structure-from-Motion (SfM)**

The foundation of any radiance field is the accurate estimation of camera poses. If the software does not know exactly where the camera was when a photo was taken, the resulting reconstruction will be a blurry, incoherent mess. This process is known as **Structure-from-Motion (SfM)**.

### **3.1 The Internal SfM Engine: A COLMAP Derivative**

Postshot utilizes an internal SfM engine that shares significant DNA with **COLMAP**, the open-source gold standard for sparse reconstruction.9 However, it is wrapped in a highly optimized C++ pipeline designed to reduce the friction associated with raw COLMAP usage.

#### **3.1.1 Feature Extraction and Matching**

The first step "behind the curtain" is **Feature Extraction**. The software analyzes every input image to identify distinctive invariant features (likely using SIFT or a similar descriptor).

* **Max Features/Frame:** This parameter 11 controls the density of the search. A value of 4,000 to 8,000 features is typical for 4K imagery. The engine then performs **Feature Matching**, comparing descriptors across image pairs to find correspondences.  
* **Geometric Verification:** Matches are filtered through geometric verification (RANSAC) to remove outliers.  
* **Incremental Reconstruction:** The engine seeds the reconstruction with a robust image pair and incrementally adds views, triangulating 3D points to form a **Sparse Point Cloud**.

This sparse point cloud serves a dual purpose:

1. **Camera Poses:** It mathematically solves the intrinsics (focal length, distortion) and extrinsics (position, rotation) of every camera.  
2. **Initialization:** The sparse points become the initial seed locations for the 3D Gaussians. 3DGS is sensitive to initialization; seeding from a random cloud often fails, whereas seeding from SfM points leads to faster convergence.12

### **3.2 Solving Scale and Orientation: The AprilTag Implementation**

A critical deficiency in monocular photogrammetry is **Scale Ambiguity**. From a set of 2D photos, it is mathematically impossible to know if a scanned chair is 1 meter tall or 100 meters tall; the geometry is identical, just scaled.  
Postshot addresses this with **AprilTag** integration.3

* **The Mechanism:** AprilTags are 2D fiducial markers (similar to QR codes) with a pre-defined pattern.  
* **Detection Pipeline:** During the ingestion phase, Postshot runs an AprilTag detection algorithm on the raw pixels. It identifies the unique ID of the tag and its 4 corner points.  
* **Pose Estimation:** By comparing the observed distortion of the tag's corners in the 2D image against the known square geometry of the tag, the software can calculate the camera's pose relative to the tag.  
* **World Alignment:** If the user specifies the physical size of the tag, Postshot scales the entire SfM solution to real-world units (meters). Furthermore, it uses the tag's orientation to define the **Up-Vector** and **Ground Plane**, automatically rotating the scene so the floor is flat.13 This automation is vital for "Digital Twin" workflows where thousands of objects must be scanned and aligned to a consistent coordinate system without manual intervention.

### **3.3 Interoperability: The "Bring Your Own Poses" Workflow**

Jawset acknowledges a fundamental truth of the industry: specialized tools are often better at specific tasks. While Postshot’s internal tracker is fast, dedicated photogrammetry suites like **RealityCapture (RC)** or **Metashape** often yield superior alignment on challenging datasets (e.g., drone surveys with low overlap or highly reflective surfaces).  
To accommodate this, Postshot supports a robust **Import Pipeline** for external tracking data 14:

* **RealityCapture:** Supports importing Component CSVs and PLY point clouds.  
* **Metashape:** Supports Camera XML export.  
* **BlockExchange:** An open XML format for block interoperability.  
* **COLMAP:** Native database (.db) and text (images.txt, cameras.txt) support.

**Use Case:** A studio scanning a large urban environment might use RealityCapture to align 10,000 drone images (leveraging RC’s out-of-core alignment engine) and then export the alignment to Postshot to train a Splat model for real-time rendering in Unreal Engine. This hybrid workflow bypasses the VRAM limitations of training a Neural Radiance Field on the massive dataset by leveraging RC's efficient sparse reconstruction first.9

## ---

**4\. The Rendering Core: Technical Analysis of Training Profiles**

Once the cameras are aligned, the core task of Postshot begins: optimizing the 3D Gaussian Splat. This is where the software deviates most significantly from standard open-source implementations. Postshot offers three distinct training profiles: **Splat3**, **Splat MCMC**, and **Splat ADC**. Each represents a different algorithmic philosophy toward densification and optimization.

### **4.1 Splat3: The Production Standard (Inside-Out)**

**Splat3** is the current default and recommended profile for general production.11 It represents a highly tuned implementation of the standard 3DGS algorithm, likely incorporating advancements similar to **Mip-Splatting**.

#### **4.1.1 Mip-Splatting and Anti-Aliasing**

Standard 3DGS suffers from severe aliasing artifacts. When a camera zooms out, a Gaussian that covered 10 pixels might shrink to cover 0.5 pixels. The rasterizer might miss it entirely or sample it poorly, causing "popping" and high-frequency noise.

* **The Solution:** Splat3 likely implements a 3D smoothing filter or specific anti-aliasing logic.15 By modifying the projected 2D covariance of the Gaussian based on the pixel footprint (clamping the minimum size), it ensures that Gaussians smoothly fade rather than snap out of existence.  
* **High-Frequency Detail:** This profile is optimized to retain high-frequency texture detail from 4K/8K images.11 It uses an "Inside-Out" reconstruction strategy, growing detail from the seed points outward.

#### **4.1.2 Memory Management: The Max Splat Cap**

A critical feature for professional use is the **Max Splat Count** parameter.11

* **Unbounded Growth:** In academic code, 3DGS models can grow indefinitely. A scene might end up with 10 million splats, consuming 30GB of VRAM and reducing render performance to a crawl.  
* **Bounded Optimization:** Splat3 allows the user to set a hard limit (e.g., 1 million splats). The optimizer is forced to work within this budget. It likely employs a priority-based pruning metric, removing splats with low opacity or low geometric contribution to make room for new splats in high-error regions. This guarantees predictable performance for real-time applications (like VR) where frame budget is non-negotiable.

### **4.2 Splat MCMC: The Probabilistic Revolution (Outside-In)**

The **Splat MCMC** profile is the most technically novel aspect of Postshot. It is based on the research paper **"3D Gaussian Splatting as Markov Chain Monte Carlo"**, presented at **NeurIPS 2024** by researchers associated with UBC Vision.17

#### **4.2.1 Stochastic Gradient Langevin Dynamics (SGLD)**

Standard 3DGS optimization is deterministic: it follows the gradient of the loss function downhill. However, the loss landscape of a 3D scene is full of "local minima"—incorrect configurations that look okay from some angles but wrong from others (e.g., "floaters" or artifacts suspended in mid-air near the camera).  
MCMC changes this by introducing **noise**.

* **Mechanism:** It treats the positions of the Gaussians as a probability distribution. The optimization uses **Stochastic Gradient Langevin Dynamics (SGLD)**, which adds a stochastic (random) noise term to the gradient update step.17  
* **The "Shake":** This noise constantly "shakes" the Gaussians. If a Gaussian is stuck in a local minimum (a floater), the noise kicks it out, allowing it to eventually settle in a more globally correct position (the actual surface).

#### **4.2.2 Relocation Strategy vs. Densification**

Standard 3DGS grows by **Cloning** (duplicating a Gaussian) or **Splitting** (breaking one big Gaussian into two small ones). This leads to uncontrolled growth.

* **MCMC Relocation:** The MCMC approach uses a fixed or controlled number of particles. Instead of creating new ones, it **relocates** existing ones. If a Gaussian is in a "dead" zone (low opacity, low contribution), it is "teleported" to a zone with high reconstruction error.12  
* **Use Case:** This profile excels at **smooth, polished surfaces** (cars, architectural interiors) where standard methods struggle with noise. It produces cleaner, more coherent surfaces with fewer floaters, though it may smooth out ultra-fine micro-textures compared to Splat3.11 It is also more robust to poor initialization.18

### **4.3 Splat ADC: The Legacy Approach**

**Splat ADC (Adaptive Density Control)** is the legacy profile.11

* **Mechanism:** It relies on a Splat Density scalar to control growth based on screen-space gradient magnitude.  
* **Limitations:** It lacks a hard splat count limit, making it dangerous for VRAM-constrained hardware. However, some users report it handles specific edge cases (like wet roads) better than the newer profiles due to its aggressive densification in high-gradient areas.21 It is generally considered deprecated in favor of Splat3.

## ---

**5\. Data Management, Performance, and Automation**

The transition from research code to production software requires rigorous resource management. 3DGS is notoriously VRAM-hungry, and Postshot includes several mechanisms to tame this beast.

### **5.1 VRAM Optimization: The Compact Workspace**

Training a radiance field requires storing not just the scene (Gaussians) but also the **Optimizer State** (gradients, momentum, and variance vectors for the Adam optimizer). This triples the memory requirement.

* **Compact Workspace:** Postshot introduces a "Compact Workspace" feature.15 While the exact implementation is proprietary, it likely involves **Paged Optimization**—offloading the optimizer states to system RAM (CPU) and only moving them to VRAM for the specific batch of Gaussians being updated. This trades a small amount of training speed for the ability to train massive scenes on cards with only 12GB or 16GB of VRAM (e.g., RTX 4070).

### **5.2 Spatial Control: Crop Boxes and ROI**

Postshot allows users to explicitly define the **Region of Interest (ROI)**.15

* **Training Focus:** When an ROI box is drawn, the stochastic sampling of rays is biased towards pixels that look at this box. The optimizer spends its compute budget refining the subject (e.g., a statue) rather than the background (e.g., the tourist crowd).  
* **Truncation:** Upon export or save, Gaussians outside the crop box or below an alpha threshold are explicitly truncated from the file.15 This reduces the .ply file size from gigabytes to megabytes, essential for web deployment or game engine integration.

### **5.3 CLI Automation for High-Volume Studios**

For e-commerce studios scanning 500 shoes a day, a GUI is a bottleneck. Postshot provides a headless **Command Line Interface (CLI)**.15

* **Pipeline Scripting:** The postshot-cli.exe allows technical directors to script the entire process:  
  Bash  
  postshot-cli.exe train \--import "C:\\Scan\_001\\Images" \--import-masks \--profile splat3 \--output "C:\\Scan\_001\\model.psht"

* **Masking Support:** The \--import-masks argument allows the ingestion of alpha masks (generated perhaps by an external AI tool like Segment Anything Model \- SAM). This creates an "Object-Centric" training loop where background pixels contribute zero loss, ensuring the network burns zero capacity on the backdrop.15

## ---

**6\. Pipeline Integration: Adobe After Effects**

One of Postshot’s unique selling points is its direct plugin for **Adobe After Effects (AE)**. This integration turns the 3DGS model into a compositable layer, bridging the gap between 3D scanning and 2.5D motion graphics.

### **6.1 Rendering Architecture: Rasterization in a Compositor**

After Effects is primarily a 2D compositor. To render 3DGS, the Postshot plugin acts as a self-contained rendering engine windowed inside an AE layer.

* **Camera Sync:** The plugin reads the AE Active Camera’s transform matrix and field of view. It passes these parameters to the Postshot engine, which rasterizes the Splat from that perspective and returns a pixel buffer to AE.  
* **Performance:** Because 3DGS rasterization is extremely fast, this occurs in near real-time, allowing motion graphics artists to animate camera moves around the scanned object directly in the AE timeline.

### **6.2 The Z-Depth Workflow**

The critical feature for VFX integration is the **Depth Pass** (Z-Buffer).24

* **Occlusion:** Standard video overlays sit on top of everything. With a Z-Depth pass, artists can use "Depth Matte" effects. If a text layer is placed at Z=500 and the scanned statue has parts at Z=400 and Z=600, the text will correctly appear *behind* the statue's nose but *in front* of its ears.  
* **32-Bit Float Requirement:** A common pitfall is bit depth. Standard 8-bit channels (0-255) do not have enough precision to represent depth linearly. Postshot requires the AE project to be in **32-bit Float** mode. The plugin writes the precise distance from the camera to the pixel into the buffer.  
* **Depth of Field:** This depth map drives standard AE lens blur effects, allowing for realistic rack-focus shots where the scanned background blurs out while the foreground remains sharp.25

### **6.3 Limitations**

The integration is limited by AE’s architecture. The Splat cannot receive shadows from AE lights, nor can it reflect AE layers (like a shape layer). It is strictly a "render-to-layer" workflow.

## ---

**7\. Pipeline Integration: Unreal Engine**

For Virtual Production and Game Development, Postshot offers plugins for **Unreal Engine 5.4 \- 5.7**.27 This integration is far deeper than the AE plugin, leveraging Epic’s advanced rendering features.

### **7.1 The RdncFieldActor**

The primary interface is the RdncFieldActor. Importing a .psht file creates a PostshotProjectAsset, which acts as the source data. The Actor handles the streaming of this data into the GPU.27

* **Level of Detail (LOD):** For massive scans, the Actor likely manages an LOD system, reducing the density of splats rendered for distant objects to maintain frame rate.

### **7.2 Heterogeneous Volumes and Shadows (UE 5.7)**

The most significant advancement in the UE integration is support for **Niagara Heterogeneous Volumes**.28

* **The Shadow Problem:** Standard 3DGS are emissive—they glow. They do not cast shadows, which makes them look "ghostly" and disconnected from the virtual scene.  
* **The Volumetric Solution:** Postshot converts the Gaussian density field into a format compatible with UE's Heterogeneous Volume renderer.  
* **Beer Shadow Maps:** Leveraging UE 5.7’s "Beer Shadow Maps" (an optimization for rendering shadows in semi-transparent media like smoke), the RdncFieldActor can cast realistic, semi-transparent shadows onto other mesh objects in the scene. Conversely, it can receive shadows from dynamic characters. This "grounding" of the scan is essential for Virtual Production, where a live actor must look like they are standing *inside* the scanned environment, not just in front of a video wall.

### **7.3 Packaging Constraints**

Currently, a limitation exists where the Postshot application must be installed on the host machine for packaged projects to run in certain configurations.27 This indicates the plugin relies on runtime linkage to Jawset’s proprietary rendering libraries (.dll) rather than baking the data down to a native Unreal asset format, which poses challenges for distributing standalone games but is acceptable for on-set Virtual Production.

## ---

**8\. Comparative Analysis and Benchmarks**

### **8.1 Postshot vs. Nerfstudio (Academic Standard)**

**Nerfstudio** is the primary open-source framework for NeRF/3DGS research.

* **Quality:** Community benchmarks indicate that Postshot’s **Splat3** profile consistently produces "crisper" and more defined results than Nerfstudio’s default splatfacto model when fed identical training data.29 The proprietary densification logic of Splat3 appears to be more aggressive in preserving edge acuity.  
* **Usability:** Nerfstudio requires a complex stack: Python, PyTorch, CUDA Toolkit, and Conda environments. Postshot is a compiled binary. For a VFX artist, the difference is between "coding" and "installing."

### **8.2 Postshot vs. Cloud Solutions (Luma AI)**

* **Training Time:** Cloud solutions queue jobs. A 1-minute video might take 30 minutes to process in the cloud. On a local RTX 4090, Postshot might resolve a preview in 2 minutes and a final quality render in 15 minutes.30  
* **Privacy:** Postshot’s offline nature is the deciding factor for enterprise clients dealing with IP-sensitive scans (e.g., unreleased car prototypes).

### **Table 2: Benchmark of Scalability and Training Time**

| Model Scale | Input Data | Typical Profile | Training Time (RTX 3090/4090) | Est. Splat Count |
| :---- | :---- | :---- | :---- | :---- |
| **Small Object** | \~50 Images | Splat MCMC | \< 5 Minutes | \~500k |
| **Room/Environment** | \~400 Images | Splat3 | 15 \- 30 Minutes | 2M \- 4M |
| **Complex Drone Scan** | \>2000 Images | Hybrid (RC Align \+ Postshot) | 1 \- 2 Hours | \>8M |

Data synthesized from community reports and release notes.16

## ---

**9\. Future Outlook: 4D and Generative Extension**

The roadmap for Postshot suggests a trajectory toward **Dynamic Scenes** and **Generative Workflows**.

* **4D Splatting:** Forum discussions and developer hints point toward **"SplatV"** or dynamic splat support.31 This involves adding a time dimension to the Gaussians, allowing them to move and deform. This is the "Holy Grail" for volumetric video, enabling the capture of moving performances without the need for a mesh or rig.  
* **Generative Sky Models:** The CLI already exposes flags for create-sky-model.15 This suggests integration with generative AI to synthesize backgrounds or fill in missing data (inpainting) where the camera didn't see.

## **Summary**

Jawset Postshot stands as a pivotal piece of software in the democratization of Neural Radiance Fields. By encapsulating the complex mathematics of **Markov Chain Monte Carlo** optimization and **Structure-from-Motion** into a production-hardened, locally processed tool, it allows VFX artists to utilize volumetric capture with the same ease as fluid simulation. Its robust integration with Unreal Engine and After Effects transforms 3DGS from a "cool tech demo" into a viable, shadow-casting, compositable asset class for high-end film and game production.

#### **Works cited**

1. Jawset Visual Computing, accessed January 27, 2026, [https://www.jawset.com/about/](https://www.jawset.com/about/)  
2. Jawset Visual Computing releases TurbulenceFD \- CG Channel, accessed January 27, 2026, [https://www.cgchannel.com/2012/03/jawset-visual-computing-releases-turbulencefd/](https://www.cgchannel.com/2012/03/jawset-visual-computing-releases-turbulencefd/)  
3. Jawset Postshot, accessed January 27, 2026, [https://www.jawset.com/](https://www.jawset.com/)  
4. Generate Gaussian Splatting models on our own PC with Postshot\! \- YouTube, accessed January 27, 2026, [https://www.youtube.com/watch?v=Q9rAAI825NM](https://www.youtube.com/watch?v=Q9rAAI825NM)  
5. Postshot User Guide, accessed January 27, 2026, [https://www.jawset.com/docs/d/Postshot+User+Guide](https://www.jawset.com/docs/d/Postshot+User+Guide)  
6. v0.5 \- Postshot User Guide, accessed January 27, 2026, [https://www.jawset.com/docs/d/Postshot+User+Guide/Release+Notes/v0.5](https://www.jawset.com/docs/d/Postshot+User+Guide/Release+Notes/v0.5)  
7. Orthophoto generation with gaussian splatting: mitigating reflective surface artifacts in imagery from low-cost sensors, accessed January 27, 2026, [https://re.public.polimi.it/retrieve/ea481750-e751-4169-b13b-abb78a68f948/isprs-archives-XLVIII-2-W8-2024-371-2024.pdf](https://re.public.polimi.it/retrieve/ea481750-e751-4169-b13b-abb78a68f948/isprs-archives-XLVIII-2-W8-2024-371-2024.pdf)  
8. Gaussian splatting to 3D model step by step. : r/GaussianSplatting \- Reddit, accessed January 27, 2026, [https://www.reddit.com/r/GaussianSplatting/comments/1e9etyq/gaussian\_splatting\_to\_3d\_model\_step\_by\_step/](https://www.reddit.com/r/GaussianSplatting/comments/1e9etyq/gaussian_splatting_to_3d_model_step_by_step/)  
9. Colmap : r/GaussianSplatting \- Reddit, accessed January 27, 2026, [https://www.reddit.com/r/GaussianSplatting/comments/1m8ieho/colmap/](https://www.reddit.com/r/GaussianSplatting/comments/1m8ieho/colmap/)  
10. Tutorial — COLMAP 3.14.0.dev0 | 5b9a079a (2025-11-14) documentation, accessed January 27, 2026, [https://colmap.github.io/tutorial.html](https://colmap.github.io/tutorial.html)  
11. Training Configuration \- Postshot User Guide, accessed January 27, 2026, [https://www.jawset.com/docs/d/Postshot+User+Guide/Interface/Training+Configuration](https://www.jawset.com/docs/d/Postshot+User+Guide/Interface/Training+Configuration)  
12. 3D Gaussian Splatting as Markov Chain Monte Carlo \- GitHub Pages, accessed January 27, 2026, [https://ubc-vision.github.io/3dgs-mcmc/paper.pdf](https://ubc-vision.github.io/3dgs-mcmc/paper.pdf)  
13. Image Set \- Postshot User Guide, accessed January 27, 2026, [https://www.jawset.com/docs/d/Postshot+User+Guide/Interface/Scene+Tree/Image+Set](https://www.jawset.com/docs/d/Postshot+User+Guide/Interface/Scene+Tree/Image+Set)  
14. v0.4 \- Postshot User Guide, accessed January 27, 2026, [https://www.jawset.com/docs/d/Postshot+User+Guide/Release+Notes/v0.4](https://www.jawset.com/docs/d/Postshot+User+Guide/Release+Notes/v0.4)  
15. v1.0 \- Postshot User Guide, accessed January 27, 2026, [https://www.jawset.com/docs/d/Postshot+User+Guide/Release+Notes/v1.0](https://www.jawset.com/docs/d/Postshot+User+Guide/Release+Notes/v1.0)  
16. PostShot \- processing time to produce 3D GaussianSplats \- Reddit, accessed January 27, 2026, [https://www.reddit.com/r/GaussianSplatting/comments/1ipk9i0/postshot\_processing\_time\_to\_produce\_3d/](https://www.reddit.com/r/GaussianSplatting/comments/1ipk9i0/postshot_processing_time_to_produce_3d/)  
17. \[2404.09591\] 3D Gaussian Splatting as Markov Chain Monte Carlo \- arXiv, accessed January 27, 2026, [https://arxiv.org/abs/2404.09591](https://arxiv.org/abs/2404.09591)  
18. 3D Gaussian Splatting as Markov Chain Monte Carlo \- OpenReview, accessed January 27, 2026, [https://openreview.net/forum?id=UCSt4gk6iX](https://openreview.net/forum?id=UCSt4gk6iX)  
19. 3D Gaussian Splatting as Markov Chain Monte Carlo \- NIPS, accessed January 27, 2026, [https://proceedings.neurips.cc/paper\_files/paper/2024/file/93be245fce00a9bb2333c17ceae4b732-Paper-Conference.pdf](https://proceedings.neurips.cc/paper_files/paper/2024/file/93be245fce00a9bb2333c17ceae4b732-Paper-Conference.pdf)  
20. Gaussian Splatting MCMC method \- PlayCanvas Forum, accessed January 27, 2026, [https://forum.playcanvas.com/t/gaussian-splatting-mcmc-method/40962](https://forum.playcanvas.com/t/gaussian-splatting-mcmc-method/40962)  
21. (Postshot) Why doesn't my gaussian splatting scene converge? : r/GaussianSplatting, accessed January 27, 2026, [https://www.reddit.com/r/GaussianSplatting/comments/1e9pzbl/postshot\_why\_doesnt\_my\_gaussian\_splatting\_scene/](https://www.reddit.com/r/GaussianSplatting/comments/1e9pzbl/postshot_why_doesnt_my_gaussian_splatting_scene/)  
22. v0.6.365 \- Postshot User Guide, accessed January 27, 2026, [https://www.jawset.com/docs/d/Postshot+User+Guide/Release+Notes/v0.6.365](https://www.jawset.com/docs/d/Postshot+User+Guide/Release+Notes/v0.6.365)  
23. Command-line Interface \- Postshot User Guide, accessed January 27, 2026, [https://www.jawset.com/docs/d/Postshot+User+Guide/Command-line+Interface](https://www.jawset.com/docs/d/Postshot+User+Guide/Command-line+Interface)  
24. Getting Started \- Postshot User Guide, accessed January 27, 2026, [https://www.jawset.com/docs/d/Postshot+User+Guide/Getting+Started](https://www.jawset.com/docs/d/Postshot+User+Guide/Getting+Started)  
25. Getting the depth buffer \- Compositing and Post Processing \- Blender Artists Community, accessed January 27, 2026, [https://blenderartists.org/t/getting-the-depth-buffer/508895](https://blenderartists.org/t/getting-the-depth-buffer/508895)  
26. Exporting Z Depth to After Effect in Maya 2017 \- Autodesk Community, accessed January 27, 2026, [https://forums.autodesk.com/t5/maya-shading-lighting-and/exporting-z-depth-to-after-effect-in-maya-2017/td-p/7291360](https://forums.autodesk.com/t5/maya-shading-lighting-and/exporting-z-depth-to-after-effect-in-maya-2017/td-p/7291360)  
27. Unreal Engine Integration \- Postshot User Guide, accessed January 27, 2026, [https://www.jawset.com/docs/d/Postshot+User+Guide/Unreal+Engine+Integration](https://www.jawset.com/docs/d/Postshot+User+Guide/Unreal+Engine+Integration)  
28. Unreal Engine 5.7 Release Notes \- Epic Games Developers, accessed January 27, 2026, [https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-5-7-release-notes](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-5-7-release-notes)  
29. Postshot has better quality splats \- due to suboptimal colmap usage/algorithm/both? \#3421, accessed January 27, 2026, [https://github.com/nerfstudio-project/nerfstudio/issues/3421](https://github.com/nerfstudio-project/nerfstudio/issues/3421)  
30. 3D Gaussian Splatting in Geosciences: A Novel High-Fidelity Approach for Digitizing Geoheritage from Minerals to Immersive Virtual Tours \- MDPI, accessed January 27, 2026, [https://www.mdpi.com/2076-3263/15/10/373](https://www.mdpi.com/2076-3263/15/10/373)  
31. New Gaussian Splatting Editor \- looking for feedback\! : r/GaussianSplatting \- Reddit, accessed January 27, 2026, [https://www.reddit.com/r/GaussianSplatting/comments/1jxu8iu/new\_gaussian\_splatting\_editor\_looking\_for\_feedback/](https://www.reddit.com/r/GaussianSplatting/comments/1jxu8iu/new_gaussian_splatting_editor_looking_for_feedback/)