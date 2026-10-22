"""Global display rendering calibrated from the ARW's embedded camera preview.

The preview supplies distribution statistics only. Full resolution pixels and
HDR highlight information always come from the high precision RAW development.
This PoC intentionally fails when that calibration reference is unavailable.
"""
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

Array = NDArray[Any]
WEIGHTS = np.array([.2126, .7152, .0722], dtype=np.float32)


def encode_srgb(rgb: Array) -> Array:
    return np.where(rgb <= .0031308, rgb * 12.92,
                    1.055 * np.maximum(rgb, 0) ** (1 / 2.4) - .055)


def _saturate(rgb: Array, amount: float) -> Array:
    luminance = (rgb @ WEIGHTS)[..., None]
    chroma = rgb - luminance
    limit = np.where(chroma > 0, (1 - luminance) / np.maximum(chroma, 1e-8),
                     np.where(chroma < 0, luminance / np.maximum(-chroma, 1e-8), 100))
    return np.asarray(np.clip(luminance + chroma * np.minimum(amount, limit.min(2, keepdims=True)), 0, 1))


def _mean_saturation(rgb: Array) -> float:
    high = rgb.max(2)
    return float(np.mean((high - rgb.min(2)) / np.maximum(high, .001)))


@dataclass(frozen=True)
class DisplayTone:
    input_luminance: Array
    output_luminance: Array
    saturation: float

    def render(self, neutral: Array) -> Array:
        luminance = neutral @ WEIGHTS
        mapped = np.interp(luminance, self.input_luminance, self.output_luminance)
        base = np.clip(neutral * (mapped / np.maximum(luminance, 1e-8))[..., None], 0, 1)
        return _saturate(base, self.saturation).astype(np.float32)


def calibrate(neutral: Array, preview: Array) -> DisplayTone:
    reference = np.where(preview <= .04045, preview / 12.92, ((preview + .055) / 1.055) ** 2.4)
    quantiles = np.linspace(.001, .999, 257)
    inputs = np.quantile(neutral @ WEIGHTS, quantiles)
    outputs = np.quantile(reference @ WEIGHTS, quantiles)
    inputs, indices = np.unique(inputs, return_index=True)
    # Exclude zero so the black endpoint remains unambiguous for interpolation.
    positive = inputs > 0
    inputs, outputs = inputs[positive], outputs[indices][positive]
    if len(inputs) < 2:
        raise ValueError('RAW has insufficient tonal variation for preview calibration')
    inputs = np.r_[0, inputs, max(4, inputs[-1] + .001)]
    outputs = np.r_[0, outputs, 1]
    base = DisplayTone(inputs, outputs, 1).render(neutral)
    target = _mean_saturation(preview)
    low, high = .5, 2.5
    for _ in range(12):
        middle = (low + high) / 2
        if _mean_saturation(encode_srgb(_saturate(base, middle))) < target:
            low = middle
        else:
            high = middle
    return DisplayTone(inputs, outputs, (low + high) / 2)
