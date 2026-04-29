import numpy as np


class IDWWindField:
    """
    Reconstruct a 2D wind field from sparse sensor measurements
    using inverse distance weighting (IDW) on wind vector components.

    Coordinate convention:
        - x, y are Cartesian coordinates in the field
        - wind direction is assumed to be meteorological "FROM" direction:
            0 deg = from North
            90 deg = from East
        - output u, v are Cartesian components:
            u > 0 means flow toward +x
            v > 0 means flow toward +y
    """

    def __init__(self, power=2.0, epsilon=1e-6):
        """
        Parameters
        ----------
        power : float
            IDW power parameter. Larger values give more weight to nearby sensors.
            Common values: 1.0 to 3.0. A good default is 2.0.
        epsilon : float
            Small number to avoid division by zero.
        """
        self.power = power
        self.epsilon = epsilon

    @staticmethod
    def speed_dir_to_uv(speed, direction_deg):
        """
        Convert meteorological wind speed/direction ("FROM" direction)
        into Cartesian velocity components (u, v).

        Meteorological convention:
            0 deg = from North
            90 deg = from East

        Cartesian convention here:
            +x = East
            +y = North

        Returns
        -------
        u, v : ndarray
            Wind components representing where the air is going TO.
        """
        speed = np.asarray(speed, dtype=float)
        direction_deg = np.asarray(direction_deg, dtype=float)

        theta = np.deg2rad(direction_deg)

        # Meteorological FROM direction -> Cartesian TO vector
        u = -speed * np.sin(theta)
        v = -speed * np.cos(theta)

        return u, v

    @staticmethod
    def uv_to_speed_dir(u, v):
        """
        Convert Cartesian velocity components (u, v) back to
        meteorological wind speed and FROM direction.

        Returns
        -------
        speed : ndarray
        direction_deg : ndarray
            Meteorological FROM direction in degrees [0, 360).
        """
        u = np.asarray(u, dtype=float)
        v = np.asarray(v, dtype=float)

        speed = np.sqrt(u**2 + v**2)

        # Convert TO vector to FROM direction
        direction_rad = np.arctan2(-u, -v)
        direction_deg = (np.rad2deg(direction_rad) + 360.0) % 360.0

        return speed, direction_deg

    def interpolate_point(self, xq, yq, sensor_x, sensor_y, sensor_u, sensor_v):
        """
        Interpolate wind components at a single query point using IDW.

        Parameters
        ----------
        xq, yq : float
            Query point coordinates
        sensor_x, sensor_y : array-like
            Sensor coordinates
        sensor_u, sensor_v : array-like
            Sensor wind components

        Returns
        -------
        uq, vq : float
            Interpolated wind components at the query point
        """
        sensor_x = np.asarray(sensor_x, dtype=float)
        sensor_y = np.asarray(sensor_y, dtype=float)
        sensor_u = np.asarray(sensor_u, dtype=float)
        sensor_v = np.asarray(sensor_v, dtype=float)

        dx = sensor_x - xq
        dy = sensor_y - yq
        dist = np.sqrt(dx**2 + dy**2)

        # If query point is exactly at a sensor, return that sensor value directly
        idx = np.argmin(dist)
        if dist[idx] < self.epsilon:
            return sensor_u[idx], sensor_v[idx]

        weights = 1.0 / (dist**self.power + self.epsilon)

        uq = np.sum(weights * sensor_u) / np.sum(weights)
        vq = np.sum(weights * sensor_v) / np.sum(weights)

        return uq, vq

    def interpolate_grid(
        self,
        sensor_x,
        sensor_y,
        sensor_speed,
        sensor_dir_deg,
        x_min=0.0,
        x_max=15.0,
        y_min=0.0,
        y_max=15.0,
        nx=31,
        ny=31
    ):
        """
        Interpolate wind field on a 2D grid.

        Parameters
        ----------
        sensor_x, sensor_y : array-like
            Sensor coordinates
        sensor_speed : array-like
            Measured wind speeds
        sensor_dir_deg : array-like
            Measured wind directions (meteorological FROM convention)
        x_min, x_max, y_min, y_max : float
            Grid bounds
        nx, ny : int
            Number of grid points in x and y

        Returns
        -------
        X, Y : 2D ndarray
            Meshgrid coordinates
        U, V : 2D ndarray
            Interpolated wind components
        S, D : 2D ndarray
            Interpolated wind speed and direction
        """
        sensor_x = np.asarray(sensor_x, dtype=float)
        sensor_y = np.asarray(sensor_y, dtype=float)
        sensor_speed = np.asarray(sensor_speed, dtype=float)
        sensor_dir_deg = np.asarray(sensor_dir_deg, dtype=float)

        if not (len(sensor_x) == len(sensor_y) == len(sensor_speed) == len(sensor_dir_deg)):
            raise ValueError("All sensor input arrays must have the same length.")

        if len(sensor_x) < 1:
            raise ValueError("At least one sensor is required.")

        sensor_u, sensor_v = self.speed_dir_to_uv(sensor_speed, sensor_dir_deg)

        x_vals = np.linspace(x_min, x_max, nx)
        y_vals = np.linspace(y_min, y_max, ny)
        X, Y = np.meshgrid(x_vals, y_vals)

        U = np.zeros_like(X, dtype=float)
        V = np.zeros_like(Y, dtype=float)

        for j in range(ny):
            for i in range(nx):
                U[j, i], V[j, i] = self.interpolate_point(
                    X[j, i], Y[j, i],
                    sensor_x, sensor_y,
                    sensor_u, sensor_v
                )

        S, D = self.uv_to_speed_dir(U, V)

        return X, Y, U, V, S, D


if __name__ == "__main__":
    # Example sensor data
    # Positions in yards over a 15 x 15 yard field
    sensor_x = [2.0, 12.0, 4.0, 11.0]
    sensor_y = [3.0, 2.0, 13.0, 12.0]

    # Example wind measurements
    # speed can be mph, m/s, etc. as long as you're consistent
    sensor_speed = [5.2, 5.5, 5.0, 5.3]

    # Meteorological FROM direction
    sensor_dir_deg = [270.0, 265.0, 275.0, 268.0]

    reconstructor = IDWWindField(power=2.0)

    X, Y, U, V, S, D = reconstructor.interpolate_grid(
        sensor_x=sensor_x,
        sensor_y=sensor_y,
        sensor_speed=sensor_speed,
        sensor_dir_deg=sensor_dir_deg,
        x_min=0.0,
        x_max=15.0,
        y_min=0.0,
        y_max=15.0,
        nx=21,
        ny=21
    )

    # Example: print wind estimate at grid center
    center_j = S.shape[0] // 2
    center_i = S.shape[1] // 2

    print("Center point:")
    print(f"x = {X[center_j, center_i]:.2f}, y = {Y[center_j, center_i]:.2f}")
    print(f"u = {U[center_j, center_i]:.3f}")
    print(f"v = {V[center_j, center_i]:.3f}")
    print(f"speed = {S[center_j, center_i]:.3f}")
    print(f"direction_from = {D[center_j, center_i]:.3f} deg")