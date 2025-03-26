import tkinter as tk
import serial
import serial.tools.list_ports
import sounddevice as sd
import numpy as np
import threading
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import queue
import time
from scipy.io.wavfile import write as write_wav
from tkinter import font

class VX2Controller:
    def __init__(self, master):
        self.master = master
        self.master.title("Yaesu VX-2 Controller")
        default_font = font.nametofont("TkDefaultFont")
        default_font.configure(size=24)
        bold_font = font.Font(family="TkDefaultFont", size=24, weight="bold")
        self.master.option_add("*Font", default_font)
        self.master.geometry("1024x768")  # Optional: Set a good default window size

        self.serial_port = None
        self.ptt_state = False
        self.stream = None
        self.running = False
        self.audio_q = queue.Queue()

        # Serial control section
        #self.port_label = tk.Label(master, text="Select Serial Port:")
        #self.port_label.pack()
        self.port_label = tk.Label(master, text="Select Serial Port:")
        self.port_label.pack(pady=5)

        self.port_var = tk.StringVar(master)
        self.refresh_ports()
        self.port_menu = tk.OptionMenu(master, self.port_var, *self.ports)
        self.port_menu.config(width=30)
        self.port_menu.pack(pady=5)

        self.refresh_button = tk.Button(master, text="Refresh Ports", command=self.refresh_ports)
        self.refresh_button.pack(pady=5)

        self.connect_button = tk.Button(master, text="Connect", command=self.connect_serial)
        self.connect_button.pack(pady=5)

        self.disconnect_button = tk.Button(master, text="Disconnect", command=self.disconnect_serial, state='disabled')
        self.disconnect_button.pack(pady=5)

        self.ptt_button = tk.Button(master, text="PTT ON", state='disabled', command=self.toggle_ptt)
        self.ptt_button.pack(pady=10)

        self.audio_button = tk.Button(master, text="Start Audio Monitor", command=self.toggle_audio_monitor)
        self.audio_button.pack(pady=10)

        self.status_label = tk.Label(master, text="Status: Disconnected", fg="red")
        self.status_label.pack(pady=10)

        # Matplotlib audio plot
        self.fig, self.ax = plt.subplots(figsize=(6, 3))
        self.line, = self.ax.plot(np.zeros(1024))
        self.ax.set_ylim(-1, 1)
        self.canvas = FigureCanvasTkAgg(self.fig, master)
        self.canvas.get_tk_widget().pack()

        # Audio buffer for recording
        self.audio_buffer = []
        self.start_time = None

    def refresh_ports(self):
        self.ports = [port.device for port in serial.tools.list_ports.comports()]
        if self.ports:
            self.port_var.set(self.ports[0])
        else:
            self.port_var.set("No Ports Found")
        if hasattr(self, 'port_menu'):
            menu = self.port_menu['menu']
            menu.delete(0, 'end')
            for port in self.ports:
                menu.add_command(label=port, command=lambda value=port: self.port_var.set(value))

    def connect_serial(self):
        port_name = self.port_var.get()
        try:
            self.serial_port = serial.Serial(port_name)
            self.serial_port.setRTS(False)
            self.status_label.config(text=f"Connected to {port_name}", fg="green")
            self.ptt_button.config(state='normal')
            self.connect_button.config(state='disabled')
            self.disconnect_button.config(state='normal')
        except Exception as e:
            self.status_label.config(text=f"Connection failed: {e}", fg="red")
            self.ptt_button.config(state='disabled')

    def disconnect_serial(self):
        if self.serial_port:
            try:
                self.serial_port.setRTS(False)
                self.serial_port.close()
                self.serial_port = None
                self.status_label.config(text="Disconnected", fg="red")
            except Exception as e:
                self.status_label.config(text=f"Error disconnecting: {e}", fg="red")
        self.ptt_button.config(state='disabled')
        self.connect_button.config(state='normal')
        self.disconnect_button.config(state='disabled')


    def toggle_ptt(self):
        if not self.serial_port:
            return
        self.ptt_state = not self.ptt_state
        self.serial_port.setRTS(self.ptt_state)
        self.ptt_button.config(text="PTT OFF" if self.ptt_state else "PTT ON")
        self.status_label.config(
            text="Transmitting..." if self.ptt_state else "Idle",
            fg="blue" if self.ptt_state else "green"
        )

    def toggle_audio_monitor(self):
        if self.running:
            self.running = False
            self.audio_button.config(text="Start Audio Monitor")
            self.stream.stop()
            self.stream.close()
            self.save_audio()
        else:
            self.running = True
            self.audio_buffer = []
            self.start_time = time.time()
            self.audio_button.config(text="Stop Audio Monitor")
            self.start_audio_thread()

    def audio_callback(self, indata, frames, time_info, status):
        if status:
            print(status)
        self.audio_q.put(indata.copy())
        self.audio_buffer.append(indata.copy())

    def update_plot(self):
        try:
            while not self.audio_q.empty():
                data = self.audio_q.get_nowait()
                self.line.set_ydata(data[:, 0])
                self.line.set_xdata(np.arange(len(data[:, 0])))
                self.ax.relim()
                self.ax.autoscale_view()
                self.canvas.draw()
        except queue.Empty:
            pass
        if self.running:
            self.master.after(50, self.update_plot)

    def start_audio_thread(self):
        self.stream = sd.InputStream(callback=self.audio_callback, channels=1, samplerate=44100, blocksize=1024)
        self.stream.start()
        self.update_plot()

    def save_audio(self):
        if not self.audio_buffer:
            return
        audio_data = np.concatenate(self.audio_buffer)
        write_wav("received_audio.wav", 44100, audio_data)
        self.status_label.config(text="Audio saved to received_audio.wav", fg="blue")

    def close(self):
        self.running = False
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
        except Exception as e:
            print("Error closing audio stream:", e)
        try:
            if self.serial_port:
                self.disconnect_serial()
                self.serial_port.setRTS(False)
                self.serial_port.close()
        except Exception as e:
            print("Error closing serial port:", e)
        self.master.quit()
        self.master.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = VX2Controller(root)
    def on_closing():
        app.close()
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

