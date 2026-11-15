# Source assets

Store models, textures and audio source files here. To import them automatically,
commit a validated Automation/Queue/*.json manifest referencing the source path.

Generated Unreal assets go under /Game/WishlessGenerated and are ignored by Git;
reproduce them from the versioned source and automation queue.

Keep manually edited .uasset/.umap files elsewhere in Content/ and version with Git LFS.
