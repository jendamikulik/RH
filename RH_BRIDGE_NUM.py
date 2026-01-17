import numpy as np

def load_zeros(path: str) -> np.ndarray:
    zs = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            zs.append(float(line))
    return np.asarray(zs, dtype=np.float64)

def window_zeros(gammas: np.ndarray, t0: float, H: float) -> np.ndarray:
    m = (gammas >= t0 - H) & (gammas <= t0 + H)
    return gammas[m]

def gaussian_weights(u: np.ndarray, sigma: float) -> np.ndarray:
    # unnormalized Gaussian is fine; we normalize via sums below
    return np.exp(-0.5 * (u / sigma) ** 2)

"""
    Smooth weighted dipole:
      b_gamma = w(gamma-t0) * (gamma - mean_w),
    where mean_w is the weighted mean of gamma in the window.
    This enforces sum b_gamma = 0 (up to FP error).
"""
"""def smooth_dipole_coeffs(gammas: np.ndarray, t0: float, sigma_w: float) -> np.ndarray:
    u = gammas - t0
    w = gaussian_weights(u, sigma=sigma_w)
    w_sum = w.sum()
    if w_sum == 0:
        raise ValueError("All weights are ~0; increase sigma_w or check window.")
    mean_w = (w * gammas).sum() / w_sum
    b = w * (gammas - mean_w)
    return b
"""

def smooth_dipole_coeffs(gammas: np.ndarray, t0: float, sigma_w: float) -> np.ndarray:
    d = gammas - t0
    w = np.exp(-0.5 * (d / sigma_w) ** 2)
    w_sum = w.sum()
    if w_sum == 0:
        raise ValueError("All weights are ~0; increase sigma_w or check window.")
    mu = (w * d).sum() / w_sum          # mean shift, small numbers
    b = w * (d - mu)
    return b


def form_factor_FT(gammas: np.ndarray, b: np.ndarray, t0: float,
                   T: float, n_omega: int = 4001) -> float:
    """
    F_T = ∫_{|ω|≤1/T} | Σ b_j e^{-i ω (γ_j - t0)} |^2 dω
    """
    if gammas.size == 0:
        return 0.0

    wmax = 1.0 / T
    omegas = np.linspace(-wmax, wmax, n_omega)

    # shift ordinates to kill huge phase constants
    d = gammas - t0

    phase = np.exp(-1j * np.outer(omegas, d))  # shape (n_omega, N)
    S = phase @ b                               # shape (n_omega,)

    integrand = np.abs(S) ** 2
    # np.trapz is deprecated; use trapezoid
    F = np.trapezoid(integrand, omegas)
    return float(F)

def scan_T(gammas: np.ndarray, b: np.ndarray, t0: float,
           T_list: np.ndarray, n_omega: int = 4001) -> np.ndarray:
    out = np.empty((T_list.size, 2), dtype=np.float64)
    for i, T in enumerate(T_list):
        out[i, 0] = T
        out[i, 1] = form_factor_FT(gammas, b, t0, float(T), n_omega=n_omega)
    return out

def fit_power_law(data: np.ndarray, eps: float = 1e-300) -> float:
    """
    Fit log F = -beta log T + c
    Returns beta_hat.
    """
    T = data[:, 0]
    F = data[:, 1]
    logT = np.log(T)
    logF = np.log(F + eps)
    slope, intercept = np.polyfit(logT, logF, 1)
    beta_hat = -slope
    return float(beta_hat)

if __name__ == "__main__":
    gammas_all = load_zeros("zeros.txt")

    # Example: choose t0 from your run or pick a percentile height
    # If you already know a good t0, set it explicitly.
    t0 = 267653396932.46216

    # Window half-width in ordinate units (tune); you used values giving N=10000
    H = 2.0e6
    gammas = window_zeros(gammas_all, t0, H)
    print("t0:", t0)
    print("min/max:", gammas.min(), gammas.max())
    print("zeros in window:", gammas.size)

    # Smooth dipole scale (sigma_w) should be comparable to H or smaller.
    # If sigma_w is too small, weights collapse; if too large, it becomes near-uniform.
    sigma_w = 0.6 * H
    b = smooth_dipole_coeffs(gammas, t0=t0, sigma_w=sigma_w)

    # DC-kill check (should be ~ 0)
    print("DC-kill residual sum b:", float(b.sum()))

    # Sweep T
    T_list = np.logspace(1, 5, 25)   # 10 ... 1e5
    data = scan_T(gammas, b, t0=t0, T_list=T_list, n_omega=4001)

    beta_hat = fit_power_law(data)
    print("beta_hat (F ~ T^{-beta}):", beta_hat)
    print("margin over 1:", beta_hat - 1.0)

    # Optional: quick stability check by refitting on the upper half of T-range
    mid = len(T_list) // 2
    beta_hat_hi = fit_power_law(data[mid:])
    print("beta_hat (upper-half T):", beta_hat_hi, "margin:", beta_hat_hi - 1.0)
