import time
from smbus2 import SMBus

AS5600_ADDR = 0x36
REG_ANGLE = 0x0E  # high byte at 0x0E, low byte at 0x0F


class AS5600:
    def __init__(self, bus_num=1, address=AS5600_ADDR):
        self.bus = SMBus(bus_num)
        self.address = address

    def close(self):
        self.bus.close()

    def read_u16_be(self, reg_high):
        high = self.bus.read_byte_data(self.address, reg_high)
        low = self.bus.read_byte_data(self.address, reg_high + 1)
        value = (high << 8) | low
        return value & 0x0FFF  # 12-bit value

    def angle_degrees(self):
        angle = self.read_u16_be(REG_ANGLE)
        return angle * 360.0 / 4096.0


def wrapped_angle_diff_deg(current, previous):
    """
    Smallest signed angle difference in degrees.
    Result is in range [-180, 180].
    """
    diff = current - previous

    if diff > 180:
        diff -= 360
    elif diff < -180:
        diff += 360

    return diff


class AS5600RPMReader:
    def __init__(self, bus_num=1, sample_interval=0.05, alpha=0.25):
        self.sensor = AS5600(bus_num=bus_num)
        self.sample_interval = sample_interval
        self.alpha = alpha

        self.prev_angle = self.sensor.angle_degrees()
        self.prev_time = time.time()
        self.rpm_smoothed = 0.0

    def read_rpm(self):
        time.sleep(self.sample_interval)

        current_angle = self.sensor.angle_degrees()
        current_time = time.time()

        dt = current_time - self.prev_time
        if dt <= 0:
            return self.rpm_smoothed

        dtheta = wrapped_angle_diff_deg(current_angle, self.prev_angle)

        rps = (dtheta / dt) / 360.0
        rpm = rps * 60.0

        # exponential smoothing
        self.rpm_smoothed = self.alpha * rpm + (1 - self.alpha) * self.rpm_smoothed

        self.prev_angle = current_angle
        self.prev_time = current_time

        return self.rpm_smoothed

    def close(self):
        self.sensor.close()


def main():
    reader = AS5600RPMReader()

    try:
        while True:
            rpm = reader.read_rpm()
            angle = reader.sensor.angle_degrees()
            print(f"Angle: {angle:7.2f} deg | RPM: {rpm:8.2f}")

    except KeyboardInterrupt:
        print("\\nStopped.")
    finally:
        reader.close()


if __name__ == "__main__":
    main()
