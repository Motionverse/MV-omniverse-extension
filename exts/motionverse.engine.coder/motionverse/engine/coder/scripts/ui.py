import omni.ui as ui
import omni.kit.ui
import omni.kit.app
import omni.kit.window.filepicker
import webbrowser
from .styles import *
from .constants import *

#
# UIController class
#
class UIController:
    def __init__(self, ext):
        self.ext = ext
        self.extension_path = omni.kit.app.get_app().get_extension_manager().get_extension_path(ext.ext_id)
        self._streaming_active = False
        self._window = ui.Window(WINDOW_NAME,width=600, height=260)

        self.build_ui()

    def build_ui(self):
        with self._window.frame:
            with ui.VStack(height=0):
                with ui.HStack():
                    #logo
                    logo_path = f"{self.extension_path}{LOGO_FILEPATH}"
                    ui.Image(logo_path, width=50,height=50,fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,alignment=ui.Alignment.CENTER)
                    ui.Spacer()
                    ui.Button(
                        CS_GOTO_BTN_TEXT,width=ui.Percent(10),  style=style_btn_goto_motionverse,alignment=ui.Alignment.RIGHT_CENTER, clicked_fn=self.launch_motionverse_website)
                
                with ui.HStack():
                    # green/red status
                    with ui.VStack(width=50, alignment=ui.Alignment.TOP):

                        self._status_circle = ui.Circle(
                            radius = 8,size_policy=ui.CircleSizePolicy.FIXED, style=style_status_circle_red
                        )

                        ui.Spacer()
                    with ui.VStack():
                        # CaptureStream device selection drop-down
                        with ui.HStack():

                            ui.Label(
                                CS_HOSTNAME_TEXT, width=ui.Percent(20), alignment=ui.Alignment.RIGHT_CENTER
                            )

                            ui.Spacer(width=CS_H_SPACING)

                            with ui.VStack(width=ui.Percent(50)):
                                ui.Spacer()
                                self.source_ip_field = ui.StringField(
                                    model=ui.SimpleStringModel(DEFAULT_IP), height=0, visible=True
                                )
                                ui.Spacer()
                            ui.Label(
                                CS_PORT_TEXT, width=ui.Percent(10), alignment=ui.Alignment.RIGHT_CENTER
                            )
                            with ui.VStack(width=ui.Percent(10)):
                                ui.Spacer()
                                self.source_port_field = ui.StringField(
                                    model=ui.SimpleStringModel(DEFAULT_PORT), height=0, visible=True
                                )
                                ui.Spacer()

                        # skeleton selection
                        with ui.HStack():

                            ui.Label(
                                SKEL_SOURCE_EDIT_TEXT, width=ui.Percent(20), alignment=ui.Alignment.RIGHT_CENTER
                            )

                            ui.Spacer(width=CS_H_SPACING)

                            with ui.VStack(width=ui.Percent(50)):
                                ui.Spacer()
                                self._skeleton_to_drive_stringfield = ui.StringField(
                                    model=ui.SimpleStringModel(SKEL_INVALID_TEXT), height=0, enabled=False
                                )
                                ui.Spacer()

                            ui.Spacer(width=CS_H_SPACING)

                            self._skel_select_button = ui.Button(
                                SKEL_SOURCE_BTN_TEXT, width=0, clicked_fn=self.select_skeleton
                            )
                        # rig selection
                        with ui.HStack():

                            ui.Label(RIG_DROPDOWN_TEXT, width=ui.Percent(20), alignment=ui.Alignment.RIGHT_CENTER)

                            ui.Spacer(width=CS_H_SPACING)

                            with ui.VStack(width=ui.Percent(75)):
                                ui.Spacer()
                                self._selected_rig_label = ui.Label("")
                                ui.Spacer()
                        # start/stop stream buttons
                        with ui.HStack():

                            ui.Spacer(width=ui.Percent(20))

                            self._start_button = ui.Button(
                                CS_START_BTN_TEXT,
                                width=0,
                                clicked_fn=self.start_streaming,
                                enabled=not self.streaming_active,
                                style=style_btn_disabled if self.streaming_active else style_btn_enabled,
                            )

                            ui.Spacer(width=CS_H_SPACING)

                            self._stop_button = ui.Button(
                                CS_STOP_BTN_TEXT,
                                width=0,
                                clicked_fn=self.stop_streaming,
                                enabled=self.streaming_active,
                                style=style_btn_enabled if self.streaming_active else style_btn_disabled,
                            )

                        ui.Spacer(height=5)
    def shutdown(self):
        self._window.frame.clear()
        self._window = None
           
    def select_skeleton(self):
        paths = omni.usd.get_context().get_selection().get_selected_prim_paths()
        if paths:
            path = paths[0]
            try:
                self.ext.init_skeletons(path)
            except Exception as ex:
                self._skeleton_to_drive_stringfield.model.set_value(SKEL_INVALID_TEXT)
            self._selected_rig_label.text = self.ext.selected_rig_name or RIG_UNSUPPORTED_TEXT

    def launch_motionverse_website(self):
        webbrowser.open_new_tab(CS_URL)

    def update_ui(self):
        if self.streaming_active:
            self._start_button.enabled = False
            self._start_button.set_style(style_btn_disabled)
            self._stop_button.enabled = True
            self._stop_button.set_style(style_btn_enabled)
        else:
            self._start_button.enabled = self.ext.ready_to_stream
            self._start_button.set_style(
                style_btn_enabled if self.ext.ready_to_stream else style_btn_disabled
            )
            self._stop_button.enabled = False
            self._stop_button.set_style(style_btn_disabled)

        if self.streaming_active:
            self._status_circle.set_style(style_status_circle_green)
        else:
            self._status_circle.set_style(style_status_circle_red)

        self._skeleton_to_drive_stringfield.model.set_value(self.ext.target_skeleton_path)
    def start_streaming(self):
        self.ext.connect()
    def stop_streaming(self):
        self.ext.disconnect("User cancelled")

    @property
    def streaming_active(self):
        return self._streaming_active

    @streaming_active.setter
    def streaming_active(self, value):
        self._streaming_active = value