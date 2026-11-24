"""Linear spectrogram as in OpenVoice's mel_processing.spectrogram_torch (MIT), using a complex STFT."""
import torch

_windows: dict = {}


def spectrogram(y: torch.Tensor, n_fft: int, hop_size: int, win_size: int) -> torch.Tensor:
    key = (win_size, y.dtype, y.device)
    if key not in _windows:
        _windows[key] = torch.hann_window(win_size).to(dtype=y.dtype, device=y.device)
    pad = int((n_fft - hop_size) / 2)
    y = torch.nn.functional.pad(y.unsqueeze(1), (pad, pad), mode="reflect").squeeze(1)
    spec = torch.stft(y, n_fft, hop_length=hop_size, win_length=win_size, window=_windows[key], center=False,
                      pad_mode="reflect", normalized=False, onesided=True, return_complex=True)
    return torch.sqrt(spec.real.pow(2) + spec.imag.pow(2) + 1e-6)
