export function lightingFor(spec) {
  const light = spec.lighting ?? {};
  return {
    ambient: light.ambient ?? 1.05,
    key: light.key ?? 2.8,
    position: light.position ?? [-3, 6, 5],
    target: light.target ?? [0, 0, 0],
    color: (light.color ?? "#ffffff").toLowerCase(),
    shadowExtent: light.shadows ? light.shadow_extent ?? 4 : null,
  };
}
