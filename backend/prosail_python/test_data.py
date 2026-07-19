import numpy as np

def get_spectral_data():
    return np.array([
        [1.5115, 6.48815e-02, 1.67340e-01, 6.66747e-02, 5.272e-01, 5.800e-05, 1.097e+02, 5.910e-01, 2.413e+00, 2.377e-01, 3.208e-02],
        [1.5115, 6.67318e-02, 1.67607e-01, 6.40556e-02, 5.262e-01, 5.852e-05, 1.037e+02, 5.980e-01, 2.413e+00, 2.373e-01, 3.195e-02],
        [1.5115, 6.85513e-02, 1.67184e-01, 6.19332e-02, 5.252e-01, 5.900e-05, 9.798e+01, 6.050e-01, 2.414e+00, 2.369e-01, 3.181e-02],
    ])

# Check if this works with test
if __name__ == "__main__":
    data = get_spectral_data()
    print(f"Shape: {data.shape}")
    print(f"First row: {data[0]}")