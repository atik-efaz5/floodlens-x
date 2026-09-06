import { inspectCell } from "../api";

function depthToColor(value, maxValue) {
  const t = maxValue > 0 ? Math.min(value / maxValue, 1) : 0;
  const r = Math.round(255 * (1 - t * 0.7));
  const g = Math.round(180 + 75 * (1 - t));
  const b = Math.round(255 - 55 * t);
  const a = value > 0 ? 0.35 + t * 0.55 : 0;
  return [r, g, b, Math.round(a * 255)];
}

function velocityToColor(value, maxValue) {
  const t = maxValue > 0 ? Math.min(value / maxValue, 1) : 0;
  return [255, Math.round(240 - 180 * t), Math.round(120 - 100 * t), Math.round((0.3 + t * 0.6) * 255)];
}

export async function sampleRasterGrid(bounds, nx, ny, inspectContext = null) {
  const samplesX = Math.min(nx, 20);
  const samplesY = Math.min(ny, 20);
  const points = [];

  for (let row = 0; row < samplesY; row += 1) {
    for (let col = 0; col < samplesX; col += 1) {
      const longitude =
        bounds.west + ((col + 0.5) / samplesX) * (bounds.east - bounds.west);
      const latitude =
        bounds.south + ((row + 0.5) / samplesY) * (bounds.north - bounds.south);
      points.push({ row, col, latitude, longitude });
    }
  }

  const chunkSize = 25;
  const samples = [];

  for (let index = 0; index < points.length; index += chunkSize) {
    const chunk = points.slice(index, index + chunkSize);
    const chunkResults = await Promise.all(
      chunk.map(async (point) => {
        const cell = inspectContext
          ? await inspectCell(point.latitude, point.longitude, inspectContext)
          : {
              depth_m: 0,
              velocity_m_s: 0,
              max_depth_m: 0,
              is_flooded: false,
            };
        return { ...point, cell };
      })
    );
    samples.push(...chunkResults);
  }

  return { samples, samplesX, samplesY };
}

export function scaleSamplesForTime(samples, timeFraction, dryThreshold = 0.001) {
  const fraction = Math.min(Math.max(timeFraction, 0), 1);
  return samples.map((sample) => ({
    ...sample,
    cell: {
      ...sample.cell,
      depth_m: sample.cell.depth_m * fraction,
      velocity_m_s: sample.cell.velocity_m_s * fraction,
      max_depth_m: sample.cell.max_depth_m * fraction,
      is_flooded: sample.cell.depth_m * fraction > dryThreshold,
    },
  }));
}

export function buildRasterDataUrl(samples, samplesX, samplesY, layerId) {
  const canvas = document.createElement("canvas");
  canvas.width = samplesX;
  canvas.height = samplesY;
  const context = canvas.getContext("2d");
  const imageData = context.createImageData(samplesX, samplesY);

  let maxValue = 0;
  for (const sample of samples) {
    if (layerId === "velocity") {
      maxValue = Math.max(maxValue, sample.cell.velocity_m_s);
    } else if (layerId === "max_depth") {
      maxValue = Math.max(maxValue, sample.cell.max_depth_m);
    } else if (layerId === "flood_extent") {
      maxValue = 1;
    } else {
      maxValue = Math.max(maxValue, sample.cell.depth_m);
    }
  }

  for (const sample of samples) {
    const pixelIndex = (sample.row * samplesX + sample.col) * 4;
    let color;

    if (layerId === "velocity") {
      color = velocityToColor(sample.cell.velocity_m_s, maxValue);
    } else if (layerId === "max_depth") {
      color = depthToColor(sample.cell.max_depth_m, maxValue);
    } else if (layerId === "flood_extent") {
      color = sample.cell.is_flooded ? [30, 64, 175, 180] : [0, 0, 0, 0];
    } else {
      color = depthToColor(sample.cell.depth_m, maxValue);
    }

    imageData.data[pixelIndex] = color[0];
    imageData.data[pixelIndex + 1] = color[1];
    imageData.data[pixelIndex + 2] = color[2];
    imageData.data[pixelIndex + 3] = color[3];
  }

  context.putImageData(imageData, 0, 0);
  return canvas.toDataURL("image/png");
}

export function buildOverlayFromSamples(samples, samplesX, samplesY, layerId, timeFraction = 1) {
  const scaled = timeFraction >= 1 ? samples : scaleSamplesForTime(samples, timeFraction);
  return buildRasterDataUrl(scaled, samplesX, samplesY, layerId);
}

export function buildArrayOverlay(array, layerId = "depth") {
  if (!array || array.length === 0) {
    return null;
  }
  const samplesY = array.length;
  const samplesX = array[0].length;
  const canvas = document.createElement("canvas");
  canvas.width = samplesX;
  canvas.height = samplesY;
  const context = canvas.getContext("2d");
  const imageData = context.createImageData(samplesX, samplesY);

  if (layerId === "flood_extent") {
    const colors = {
      0: [148, 163, 184, 40],
      1: [30, 64, 175, 200],
      2: [234, 88, 12, 200],
      3: [147, 51, 234, 200],
    };
    for (let row = 0; row < samplesY; row += 1) {
      for (let col = 0; col < samplesX; col += 1) {
        const pixelIndex = (row * samplesX + col) * 4;
        const color = colors[array[row][col]] || colors[0];
        imageData.data[pixelIndex] = color[0];
        imageData.data[pixelIndex + 1] = color[1];
        imageData.data[pixelIndex + 2] = color[2];
        imageData.data[pixelIndex + 3] = color[3];
      }
    }
  } else {
    let maxAbs = 0;
    for (let row = 0; row < samplesY; row += 1) {
      for (let col = 0; col < samplesX; col += 1) {
        maxAbs = Math.max(maxAbs, Math.abs(array[row][col]));
      }
    }
    for (let row = 0; row < samplesY; row += 1) {
      for (let col = 0; col < samplesX; col += 1) {
        const pixelIndex = (row * samplesX + col) * 4;
        const value = array[row][col];
        const t = maxAbs > 0 ? value / maxAbs : 0;
        const r = t >= 0 ? 220 : Math.round(30 + 90 * (1 + t));
        const g = Math.round(80 + 80 * (1 - Math.abs(t)));
        const b = t < 0 ? 220 : Math.round(30 + 90 * (1 - t));
        imageData.data[pixelIndex] = r;
        imageData.data[pixelIndex + 1] = g;
        imageData.data[pixelIndex + 2] = b;
        imageData.data[pixelIndex + 3] = Math.round(60 + Math.abs(t) * 160);
      }
    }
  }

  context.putImageData(imageData, 0, 0);
  return canvas.toDataURL("image/png");
}
