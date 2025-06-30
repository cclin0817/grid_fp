
✅ 還原內容如下：

#!/CAD/TCD_BE_CENTRAL/cclin/python/bin/python3
################################
# File Name   : main.py
# Author      : cclinaz
# Created On  : 2024-07-12 17:07:48
# Description : 
################################
import time
import json
import argparse
import os
import re
import csv
import ast
import tkinter as tk
import webcolors
from copy import deepcopy
import log
from tkinter import messagebox, filedialog
import tkinter.simpledialog as simpledialog

def darken_color(color_name, darken_factor=0.7):
    try:
        rgb = webcolors.name_to_rgb(color_name)
        r, g, b = [int(c * darken_factor) for c in rgb]
        return webcolors.rgb_to_hex((r, g, b))
    except ValueError as e:
        print(f"Error: {e}")
        return None

def read_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--project_name', default='mye', help='This is an example argument.')
    args = vars(parser.parse_args())
    return args

def read_block_config(filename):
    shape_buttons = {}
    shape_colors = {}
    shape_pinsides = {}
    with open(filename, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            block_name = row['block_name']
            width = int(row['width'])
            height = int(row['height'])
            color = row['color']
            pinside = ast.literal_eval(row['pinside'])
            buttons = [(dx, dy) for dy in range(height) for dx in range(width)]
            shape_buttons[block_name] = buttons
            shape_colors[block_name] = color
            shape_pinsides[block_name] = pinside

    return shape_buttons, shape_colors, shape_pinsides

def read_project_config(filename):
    designs = []
    with open(filename, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            design_info = {
                'design_name': row['design_name'],
                'grid_width': int(row['grid_width']),
                'grid_height': int(row['grid_height']),
            }
            designs.append(design_info)
    return designs

class CustomDirectionDialog(simpledialog.Dialog):
    def body(self, master):
        tk.Label(master, text="Select the direction for auto-repeat:").grid(row=0)
        self.var = tk.StringVar(master)
        self.var.set("V")
        self.options = ["V", "H"]
        self.option_menu = tk.OptionMenu(master, self.var, *self.options)
        self.option_menu.grid(row=0, column=1)
        return self.option_menu

    def apply(self):
        self.result = self.var.get()

class BlockObject:
    def __init__(self, cell_name, x, y, block_shape, orientation):
        self.data = {}
        self.data['cell_name'] = cell_name
        self.data['shape_ids'] = []
        self.data['x'] = x
        self.data['y'] = y
        self.data['orientation'] = orientation

        self.block_shape = block_shape
        self.llx_in_canvas = self.data['x']
        self.lly_in_canvas = self.data['y']
        self.urx_in_canvas = self.llx_in_canvas + max(dx for dx, dy in self.block_shape)
        self.ury_in_canvas = self.lly_in_canvas + max(dy for dx, dy in self.block_shape)

    def update_location(self, x, y):
        self.data['x'] = x
        self.data['y'] = y
        self.llx_in_canvas = self.data['x']
        self.lly_in_canvas = self.data['y']
        self.urx_in_canvas = self.llx_in_canvas + max(dx for dx, dy in self.block_shape)
        self.ury_in_canvas = self.lly_in_canvas + max(dy for dx, dy in self.block_shape)

    def update_orientation(self):
        orientations = ['R0', 'MX', 'MY', 'R180', 'R90']
        next_index = (orientations.index(self.data['orientation']) + 1) % len(orientations)
        orientation = orientations[next_index]
        self.data['orientation'] = orientation

        #if orientation == 'R0' or orientation == 'R90':
        #    ori_width = max(dx for dx, dy in self.block_shape)+1
        #    ori_height = max(dy for dx, dy in self.block_shape)+1
        #    self.block_shape = [(dx, dy) for dy in range(ori_width) for dx in range(ori_height)]
        #    self.urx_in_canvas = self.llx_in_canvas + max(dx for dx, dy in self.block_shape)
        #    self.ury_in_canvas = self.lly_in_canvas + max(dy for dx, dy in self.block_shape)

class BlockPlacement(tk.Tk):
    def __init__(self, PROJ_NAME, DESIGN_NAME, GRID_WIDTH, GRID_HEIGHT, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PROJ_NAME          = PROJ_NAME
        self.DESIGN_NAME        = DESIGN_NAME
        self.GRID_WIDTH         = GRID_WIDTH
        self.GRID_HEIGHT        = GRID_HEIGHT
        self.INITIAL_CELL_SIZE  = int(min(self.winfo_screenwidth()/(2*GRID_WIDTH), (self.winfo_screenheight()-100)/GRID_HEIGHT) * 100)/100

        self.result_dir = 'output/' + self.PROJ_NAME
        self.title(self.PROJ_NAME + " " +self.DESIGN_NAME + " placement GUI")
        # Variable initialization
        csv_name = 'input/' +PROJ_NAME+ '/'+PROJ_NAME+'_'+DESIGN_NAME+'.csv'
        log.logger.info(f"Reading design spec. form {csv_name}")
        self.SHAPE_BUTTONS, self.SHAPE_COLORS, self.SHAPE_PINSIDES = read_block_config(csv_name)
        self.cell_size = self.INITIAL_CELL_SIZE
        self.canvas_width = self.GRID_WIDTH * self.cell_size
        self.canvas_height = self.GRID_HEIGHT * self.cell_size
        self.block_objects = {}
        # Variables for moving selected_blocks
        self.selected_blocks = {}
        # Variables for adding guideline
        self.block_id_for_adding_guideline = {}
        self.guideline_ids = []
        self.selected_shape = None
        self.grid_state = [[None for _ in range(self.GRID_HEIGHT)] for _ in range(self.GRID_WIDTH)]
        self.drag_rect = None
        self.drag_canvas_x = None
        self.drag_canvas_y = None
        self.drag_grid_start_x = None
        self.drag_grid_start_y = None

        if not os.path.exists(self.result_dir): os.makedirs(self.result_dir)
        #print("Init cell size", self.cell_size)

        # Frame for Canvas and Scrollbars
        self.canvas_frame = tk.Frame(self)
        self.canvas_frame.grid(row=0, column=0, sticky="nsew")

        # Creating the Canvas
        self.grid_canvas = tk.Canvas(self.canvas_frame, width=self.canvas_width,
                                     height=self.canvas_height, bg='white',
                                     scrollregion=(0, 0, self.canvas_width, self.canvas_height))
        self.grid_canvas.grid(row=0, column=0, sticky="nsew", padx=10, pady=0)

        # Scrollbars
        self.hbar = tk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL, command=self.grid_canvas.xview)
        self.hbar.grid(row=1, column=0, sticky="ew")
        self.vbar = tk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL, command=self.grid_canvas.yview)
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.grid_canvas.config(xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)

        # Frame for other toolbar
        self.shapes_frame = tk.Frame(self)
        self.shapes_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.bind("<Left>", self.scroll_left)
        self.bind("<Right>", self.scroll_right)
        self.bind("<Up>", self.scroll_up)
        self.bind("<Down>", self.scroll_down)
        self.bind("f", self.fit_fp)
        self.bind("a", self.move_left)
        self.bind("d", self.move_right)
        self.bind("s", self.move_down)
        self.bind("w", self.move_up)
        self.bind("c", self.duplicate_main)
        self.bind("t", self.move_to)
        self.bind("x", self.swap_main)
        self.focus_set()

        # Reset cell size
        self.reset_button = tk.Button(self.shapes_frame, text="Fit Floorplan", command=self.fit_fp)
        self.reset_button.pack(pady=(0,10))
        self.save_button = tk.Button(self.shapes_frame, text="Save Placement", command=self.save_to_file)
        self.save_button.pack(pady=(0, 10))
        self.load_button = tk.Button(self.shapes_frame, text="Load Default Placement", command=lambda: self.load_from_file(True))
        self.load_button.pack(pady=(0, 10))
        #self.load_button = tk.Button(self.shapes_frame, text="Load Specific Placement", command=lambda: self.load_from_file(False))
        #self.load_button.pack(pady=(0, 10))
        #self.load_button = tk.Button(self.shapes_frame, text="Clear Floorplan", command=self.clear_fp)
        #self.load_button.pack(pady=(0, 10))

        # Mode selection
        self.mode = tk.StringVar(value="Place")
        self.mode_label = tk.Label(self.shapes_frame, text="Mode: Place")
        self.mode_label.pack(pady=(0, 10))
        tk.Radiobutton(self.shapes_frame, text="Place", variable=self.mode, value="Place", command=self.update_mode).pack(anchor=tk.W)
        tk.Radiobutton(self.shapes_frame, text="Delete", variable=self.mode, value="Delete", command=self.update_mode).pack(anchor=tk.W)
        tk.Radiobutton(self.shapes_frame, text="Delete Region", variable=self.mode, value="Delete Region", command=self.update_mode).pack(anchor=tk.W)
        tk.Radiobutton(self.shapes_frame, text="Change Orientation", variable=self.mode, value="Change Orientation", command=self.update_mode).pack(anchor=tk.W)
        tk.Radiobutton(self.shapes_frame, text="Place Blockage", variable=self.mode, value="Place Blockage", command=self.update_mode).pack(anchor=tk.W)
        tk.Radiobutton(self.shapes_frame, text="Delete Blockage", variable=self.mode, value="Delete Blockage", command=self.update_mode).pack(anchor=tk.W)
        tk.Radiobutton(self.shapes_frame, text="Select w/i blockage (move:w/a/s/d/t) (duplicate:c) (swap:x)", variable=self.mode, value="Select wi blockage", command=self.update_mode).pack(anchor=tk.W)
        tk.Radiobutton(self.shapes_frame, text="Select w/o blockage (move:w/a/s/d/t) (duplicate:c) (swap:x)", variable=self.mode, value="Select wo blockage", command=self.update_mode).pack(anchor=tk.W)

        # Create shape selection buttons
        num_frames = 5
        self.shape_frames = []
        for i in range(num_frames):
            frame = tk.Frame(self.shapes_frame)
            frame.pack(side=tk.LEFT, fill=tk.Y, expand=True, padx=(5, 5))  # Adjust padding as needed
            self.shape_frames.append(frame)

        shapes_list = list(self.SHAPE_BUTTONS.keys())
        for index, shape in enumerate(shapes_list):
            parent_frame = self.shape_frames[index % num_frames]
            shape_frame = tk.Frame(parent_frame)
            shape_frame.pack(pady=5)
            largest_x = float('-inf')
            largest_y = float('-inf')
            for x, y in self.SHAPE_BUTTONS[shape]:
                if x > largest_x: largest_x = x
                if y > largest_y: largest_y = y
            btn_canvas = tk.Canvas(shape_frame, width=(largest_x+1)*self.INITIAL_CELL_SIZE//2, height=(largest_y+1)*self.INITIAL_CELL_SIZE//2, bg='white', highlightthickness=1, highlightbackground="black")
            btn_canvas.shape = shape
            btn_canvas.bind("<Button-1>", self.select_shape)
            self.draw_shape_bottoms(btn_canvas, shape, self.SHAPE_COLORS[shape])
            btn_canvas.pack(side=tk.BOTTOM)
            tk.Label(shape_frame, text=shape).pack(side=tk.BOTTOM)

        self.draw()

        self.grid_canvas.bind("<Button-1>", self.canvas_operations)
        self.grid_canvas.bind("<Button-3>", self.add_guide_line)
        self.grid_canvas.bind("<Button-4>", self.zoom_in_on_mouse_wheel)
        self.grid_canvas.bind("<Button-5>", self.zoom_out_on_mouse_wheel)
        self.grid_canvas.bind("<B1-Motion>", self.on_drag)
        self.grid_canvas.bind("<ButtonRelease-1>", self.on_release)
        #self.grid_canvas.bind("<Button>", self.print_mouse_button_code)

    def print_mouse_button_code(self, event):
        log.logger.info(f"Mouse button pressed: {event.num}")

    def swap_main(self, event):
        if len(self.selected_blocks) == 0:
            messagebox.showwarning("Swap Warning", f"No block selected.")
            return

        if self.selected_shape == None:
            messagebox.showwarning("Swap Warning", f"Select the expected block for swapping.")
            return

        for block_object in self.selected_blocks:
            self.swap_block(block_object)

    def swap_block(self, block_object):
        if self.SHAPE_BUTTONS[block_object.data['cell_name']] == self.SHAPE_BUTTONS[self.selected_shape]:
            block_object.data['cell_name'] = self.selected_shape
            self.draw_block(block_object)
        else:
            messagebox.showwarning("Swap Warning", f"Cannot swap blocks with different dimension ({self.selected_shape}).")

    def duplicate_main(self, event):
        if len(self.selected_blocks) == 0:
            messagebox.showwarning("Duplicate Warning", f"No block selected.")
            return

        dialog = CustomDirectionDialog(self)
        direction = dialog.result
        interval = simpledialog.askinteger("Input", "Enter the expected interval:", parent=self, minvalue=0)

        if direction is None or interval is None: return

        for block_object in self.selected_blocks:
            self.duplicate_block(block_object, direction, interval)

    def duplicate_block(self, block_object, direction, interval):
        start_x, start_y = block_object.data['x'], block_object.data['y']
        block_width = max(dx for dx, dy in block_object.block_shape)+1
        block_height = max(dy for dx, dy in block_object.block_shape)+1

        if direction in ("V"):
            for i in range(1, self.GRID_HEIGHT):
                new_y = start_y + i * (interval + block_height)
                if new_y < self.GRID_HEIGHT and self.is_legal_location(start_x, new_y, block_object.data['cell_name'], False):
                    new_block = BlockObject(block_object.data['cell_name'], start_x, new_y, block_object.block_shape, 'R0')
                    self.draw_block(new_block)
                    self.block_objects[id(new_block)] = new_block

        if direction in ("H"):
            for i in range(1, self.GRID_WIDTH):
                new_x = start_x + i * (interval + block_width)
                if new_x < self.GRID_WIDTH and self.is_legal_location(new_x, start_y, block_object.data['cell_name'], False):
                    new_block = BlockObject(block_object.data['cell_name'], new_x, start_y, block_object.block_shape, 'R0')
                    self.draw_block(new_block)
                    self.block_objects[id(new_block)] = new_block

    def can_move(self, x_offset, y_offset):
        block_ids = [id(block) for block in self.selected_blocks]
        new_grid_state = deepcopy(self.grid_state)
        for x in range(len(new_grid_state)):
            for y in range(len(new_grid_state[0])):
                if new_grid_state[x][y] in block_ids:
                    new_grid_state[x][y] = None

        for block in self.selected_blocks:
            new_llx = block.llx_in_canvas + x_offset
            new_lly = block.lly_in_canvas + y_offset
            new_urx = block.urx_in_canvas + x_offset
            new_ury = block.ury_in_canvas + y_offset

            # Check the horizontal edges if there is a horizontal offset
            for y in range(new_lly, new_ury + 1):
                x = new_llx if x_offset < 0 else new_urx
                if not self.is_position_free(x, y, new_grid_state):
                    return False

            # Check the vertical edges if there is a vertical offset
            for x in range(new_llx, new_urx + 1):
                y = new_lly if y_offset < 0 else new_ury
                if not self.is_position_free(x, y, new_grid_state):
                    return False
        return True

    def is_position_free(self, x, y, grid_state):
        # Ensure the position does not exceed the bounds of the grid_state
        if (0 <= x < len(grid_state)) and (0 <= y < len(grid_state[0])):
            if grid_state[x][y] is not None:
                messagebox.showwarning("Move Warning", "Cannot move in this direction, position is occupied!")
                return False
            else:
                return True
        else:
            messagebox.showwarning("Move Warning", "Cannot move in this direction, out of boundaries!")
            return False

    def move(self, x_offset, y_offset):
        if len(self.selected_blocks) == 0:
            messagebox.showwarning("Move Warning", f"No block selected.")
            return False

        if not self.can_move(x_offset, y_offset): return False

        for block in self.selected_blocks:
            # clean up grid_state
            for dx, dy in block.block_shape:
                grid_x, grid_y = block.data['x'] + dx, block.data['y'] + dy
                self.grid_state[grid_x][grid_y] = None
            block.update_location(block.data['x'] + x_offset, block.data['y'] + y_offset)
            self.draw_block(block)
        return True

    def move_left(self, event):
        self.move(-1, 0)

    def move_right(self, event):
        self.move(1, 0)

    def move_up(self, event):
        self.move(0, -1)

    def move_down(self, event):
        self.move(0, 1)

    def move_to(self, event):
        # Ensure only one block is selected
        if len(self.selected_blocks) != 1:
            messagebox.showwarning("Move Warning", "Only support one selected block.")
            return False

        # Retrieve the single selected block
        selected_block = next(iter(self.selected_blocks.keys()))

        # Prompt user for target position
        target_position = simpledialog.askstring("Move To", "Enter target position (e.g., A42):")
        if not target_position:
            return False

        # Convert Excel-like coordinates to grid coordinates
        match = re.match(r"([A-Za-z]+)([0-9]+)", target_position)
        if not match:
            messagebox.showwarning("Move Warning", "Invalid position format.")
            return False

        col_str, row_str = match.groups()
        col = self.excel_col_to_index(col_str)
        row = int(row_str) - 1  # Assuming grid is 0-indexed for rows

        # Calculate offsets based on the selected block
        current_x, current_y = selected_block.data['x'], selected_block.data['y']
        x_offset = col - current_x
        y_offset = row - current_y

        if not self.can_move_to(x_offset, y_offset, selected_block):
            return False

        # Move the block
        for dx, dy in selected_block.block_shape:
            grid_x, grid_y = selected_block.data['x'] + dx, selected_block.data['y'] + dy
            self.grid_state[grid_x][grid_y] = None
        selected_block.update_location(selected_block.data['x'] + x_offset, selected_block.data['y'] + y_offset)
        self.draw_block(selected_block)
        return True

    def can_move_to(self, x_offset, y_offset, block):
        for dx, dy in block.block_shape:
            new_x = block.data['x'] + dx + x_offset
            new_y = block.data['y'] + dy + y_offset
            if not (0 <= new_x < self.GRID_WIDTH and 0 <= new_y < self.GRID_HEIGHT):
                messagebox.showwarning("Move Warning", "Cannot move to this location, out of boundaries!")
                return False
            if self.grid_state[new_x][new_y] is not None and self.grid_state[new_x][new_y] != id(block):
                messagebox.showwarning("Move Warning", "Cannot move in this direction, position is occupied!")
                return False
        return True

    def excel_col_to_index(self, col_str):
        """Convert Excel column letter(s) to a 0-indexed column number."""
        col = 0
        for char in col_str.upper():
            col = col * 26 + (ord(char) - ord('A') + 1)
        return col - 1  # Adjust for 0-based index

    def scroll_left(self, event):
        self.grid_canvas.xview_scroll(-1, "units")

    def scroll_right(self, event):
        self.grid_canvas.xview_scroll(1, "units")

    def scroll_up(self, event):
        self.grid_canvas.yview_scroll(-1, "units")

    def scroll_down(self, event):
        self.grid_canvas.yview_scroll(1, "units")

    def add_guide_line(self, event):
        self.guide_lines = []
        canvas_x = self.grid_canvas.canvasx(event.x)
        canvas_y = self.grid_canvas.canvasy(event.y)
        x, y = int(canvas_x // self.cell_size), int(canvas_y // self.cell_size)
        if self.grid_state[x][y] is None:
            messagebox.showwarning("Invalid ioperation", "No object in the location.")
            return

        block_id = self.grid_state[x][y]
        if block_id not in self.block_id_for_adding_guideline:
            self.block_id_for_adding_guideline[block_id] = True
        else:
            del self.block_id_for_adding_guideline[block_id]
        self.draw_guide_line()
        #print("Number of elements in block_id_for_adding_guideline:", len(self.block_id_for_adding_guideline))

    def draw_guide_line(self):
        for line_id in self.guideline_ids: self.grid_canvas.delete(line_id)
        self.guideline_ids = []

        for block_id in self.block_id_for_adding_guideline.keys():
            if block_id not in self.block_objects.keys(): continue
            block_object = self.block_objects[block_id]
            line_width = 2
            color = "purple"
            self.guideline_ids.append(self.grid_canvas.create_line(block_object.llx_in_canvas*self.cell_size, 0, block_object.llx_in_canvas*self.cell_size, self.canvas_height, fill=color, width=line_width))
            self.guideline_ids.append(self.grid_canvas.create_line((block_object.urx_in_canvas+1)*self.cell_size, 0, (block_object.urx_in_canvas+1)*self.cell_size, self.canvas_height, fill=color, width=line_width))
            self.guideline_ids.append(self.grid_canvas.create_line(0, block_object.lly_in_canvas*self.cell_size, self.canvas_width, block_object.lly_in_canvas*self.cell_size, fill=color, width=line_width))
            self.guideline_ids.append(self.grid_canvas.create_line(0, (block_object.ury_in_canvas+1)*self.cell_size, self.canvas_width, (block_object.ury_in_canvas+1)*self.cell_size, fill=color, width=line_width))
            for dx, dy in block_object.block_shape:
                grid_x, grid_y = block_object.data['x'] + dx, block_object.data['y'] + dy
                self.guideline_ids.append(self.grid_canvas.create_rectangle(grid_x*self.cell_size, grid_y*self.cell_size, (grid_x+1)*self.cell_size, (grid_y+1)*self.cell_size, fill=color, outline=''))

    def on_drag(self, event):
        if self.mode.get() in ['Place Blockage', 'Delete Blockage', 'Select wi blockage', 'Select wo blockage', 'Delete Region']:
            canvas_x = self.grid_canvas.canvasx(event.x)
            canvas_y = self.grid_canvas.canvasy(event.y)
            if self.drag_rect:
                self.grid_canvas.delete(self.drag_rect)
            self.drag_rect = self.grid_canvas.create_rectangle(self.drag_canvas_x, self.drag_canvas_y, canvas_x, canvas_y, outline='blue', dash=(4, 2))
            #print(self.drag_canvas_x, self.drag_canvas_y, event.x, event.y)

    def on_release(self, event):
        if self.mode.get() in ['Place Blockage', 'Delete Blockage', 'Select wi blockage', 'Select wo blockage', 'Delete Region']:

            if self.drag_rect:
                self.grid_canvas.delete(self.drag_rect)
            self.drag_rect = None  # Reset drag rectangle

            canvas_x = self.grid_canvas.canvasx(event.x)
            canvas_y = self.grid_canvas.canvasy(event.y)

            # Convert canvas coordinates to grid coordinates
            self.drag_grid_end_x, self.drag_grid_end_y = int(canvas_x // self.cell_size), int(canvas_y // self.cell_size)

            x_start = min(self.drag_grid_start_x, self.drag_grid_end_x)
            x_end = max(self.drag_grid_start_x, self.drag_grid_end_x)
            y_start = min(self.drag_grid_start_y, self.drag_grid_end_y)
            y_end = max(self.drag_grid_start_y, self.drag_grid_end_y)

            if self.mode.get() == "Place Blockage":
                for x in range(x_start, x_end + 1):
                    for y in range(y_start, y_end + 1):
                        if 0 <= x < self.GRID_WIDTH and 0 <= y < self.GRID_HEIGHT and self.grid_state[x][y] is None:
                            if not self.is_legal_location(x, y, 'Blockage', False): continue
                            block_object = BlockObject('Blockage', x, y, self.SHAPE_BUTTONS['Blockage'], 'R0')
                            self.draw_block(block_object)
                            self.block_objects[id(block_object)] = block_object
            elif self.mode.get() in ["Delete Blockage", "Delete Region"]:
                for x in range(x_start, x_end + 1):
                    for y in range(y_start, y_end + 1):
                        if 0 <= x < self.GRID_WIDTH and 0 <= y < self.GRID_HEIGHT and self.grid_state[x][y] is not None:
                            block_id = self.grid_state[x][y]
                            if self.mode.get() == "Delete Blockage" and self.block_objects[block_id].data['cell_name'] != 'Blockage': continue
                            for obj_id in self.block_objects[block_id].data['shape_ids']:
                                self.grid_canvas.delete(obj_id)
                            del self.block_objects[block_id]
                            for i in range(len(self.grid_state)):
                                for j in range(len(self.grid_state[i])):
                                    if self.grid_state[i][j] == block_id: self.grid_state[i][j] = None
            elif self.mode.get() == "Select wi blockage":
                self.selected_blocks = {}
                for x in range(x_start, x_end + 1):
                    for y in range(y_start, y_end + 1):
                        if 0 <= x < self.GRID_WIDTH and 0 <= y < self.GRID_HEIGHT and self.grid_state[x][y] is not None:
                            block_id = self.grid_state[x][y]
                            if self.block_objects[block_id] not in self.selected_blocks:
                                self.selected_blocks[self.block_objects[block_id]] = True
                log.logger.info(f"Select {len(self.selected_blocks)} blocks")
                self.update_cell_size(self.cell_size)
            elif self.mode.get() == "Select wo blockage":
                self.selected_blocks = {}
                for x in range(x_start, x_end + 1):
                    for y in range(y_start, y_end + 1):
                        if 0 <= x < self.GRID_WIDTH and 0 <= y < self.GRID_HEIGHT and self.grid_state[x][y] is not None:
                            block_id = self.grid_state[x][y]
                            if self.block_objects[block_id] not in self.selected_blocks:
                                if self.block_objects[block_id].data['cell_name'] == 'Blockage': continue
                                self.selected_blocks[self.block_objects[block_id]] = True
                log.logger.info(f"Select {len(self.selected_blocks)} blocks")
                self.update_cell_size(self.cell_size)

    def update_cell_size(self, size):
        size = int(size*100)/100
        #log.logger.info(f"Update cell size {size}")
        self.cell_size = size
        self.canvas_width = self.GRID_WIDTH * self.cell_size
        self.canvas_height = self.GRID_HEIGHT * self.cell_size
        self.grid_canvas.config(scrollregion=(0, 0, self.canvas_width, self.canvas_height))
        self.draw()

    def fit_fp(self, event = None):
        self.update_cell_size(self.INITIAL_CELL_SIZE)

    def zoom_in_on_mouse_wheel(self, event):
        self.update_cell_size(self.cell_size*1.1)

    def zoom_out_on_mouse_wheel(self, event):
        if self.cell_size > self.INITIAL_CELL_SIZE - 1:
            self.update_cell_size(self.cell_size*0.9)
        #else:
        #    log.logger.info(f"Already reach minimal cell size")

    def draw_shape_bottoms(self, canvas, shape, color):
        if shape == "TSV":
            min_x = min(dx for dx, dy in self.SHAPE_BUTTONS[shape])
            min_y = min(dy for dx, dy in self.SHAPE_BUTTONS[shape])
            max_x = max(dx for dx, dy in self.SHAPE_BUTTONS[shape])
            max_y = max(dy for dx, dy in self.SHAPE_BUTTONS[shape])
            canvas.create_oval(min_x*self.cell_size//2, (max_y+1)*self.cell_size//2, (max_x+1)*self.cell_size//2, min_y*self.cell_size//2, fill=color, outline='')
        else:
            for x, y in self.SHAPE_BUTTONS[shape]:
                canvas.create_rectangle(x*self.cell_size//2, y*self.cell_size//2, (x+1)*self.cell_size//2, (y+1)*self.cell_size//2, fill=color, outline='')

    def select_shape(self, event):
        self.selected_shape = event.widget.shape
        messagebox.showwarning("Select object", "Select block " + self.selected_shape)

    def is_legal_location(self, x, y, shape, warning):
        for dx, dy in self.SHAPE_BUTTONS[shape]:
            grid_x, grid_y = x + dx, y + dy
            if grid_x < 0 or grid_x >= self.GRID_WIDTH or grid_y < 0 or grid_y >= self.GRID_HEIGHT or self.grid_state[grid_x][grid_y] is not None:
                if warning: messagebox.showwarning("Invalid Placement", "Cannot place shape here. Space is already occupied or out of bounds.")
                return False
        return True

    def canvas_operations(self, event):
        canvas_x = self.grid_canvas.canvasx(event.x)
        canvas_y = self.grid_canvas.canvasy(event.y)

        # Convert canvas coordinates to grid coordinates
        x, y = int(canvas_x // self.cell_size), int(canvas_y // self.cell_size)

        if x > self.GRID_WIDTH or y > self.GRID_HEIGHT:
            messagebox.showwarning("Select object", "Index out of range ")
            return

        if self.mode.get() == "Place":
            if not self.selected_shape: return
            if not self.is_legal_location(x, y, self.selected_shape, True): return

            block_object = BlockObject(self.selected_shape, x, y, self.SHAPE_BUTTONS[self.selected_shape], 'R0')
            self.draw_block(block_object)
            self.block_objects[id(block_object)] = block_object
        elif self.mode.get() == "Delete":
            if self.grid_state[x][y] is None:
                messagebox.showwarning("Invalid deletion", "No object in the deleteing location.")
                return

            block_id = self.grid_state[x][y]
            for obj_id in self.block_objects[block_id].data['shape_ids']:
                self.grid_canvas.delete(obj_id)
            del self.block_objects[block_id]
            for i in range(len(self.grid_state)):
                for j in range(len(self.grid_state[i])):
                    if self.grid_state[i][j] == block_id: self.grid_state[i][j] = None
            log.logger.info(f"{len(self.block_objects)} blocks existed in the floorplan.")
        elif self.mode.get() in ['Place Blockage', 'Delete Blockage', 'Select wi blockage', 'Select wo blockage', 'Delete Region']:
            self.drag_canvas_x, self.drag_canvas_y = canvas_x, canvas_y
            self.drag_grid_start_x, self.drag_grid_start_y = x, y
        elif self.mode.get() == "Change Orientation":
            if self.grid_state[x][y] is None:
                messagebox.showwarning("Invalid operation", "No object in the location.")
                return

            block_object = self.block_objects[self.grid_state[x][y]]
            block_object.update_orientation()

            #block_id = self.grid_state[x][y]
            #while(1):
            #    self.selected_blocks = {}
            #    self.selected_blocks[self.block_objects[block_id]] = True
            #    if self.move(0, 0) == True: break
            #    block_object.update_orientation()

            ## clear self.selected_blocks and re-draw
            #self.selected_blocks = {}
            #for i in range(len(self.grid_state)):
            #    for j in range(len(self.grid_state[i])):
            #        if self.grid_state[i][j] == block_id: self.grid_state[i][j] = None
            self.draw_block(block_object)

    def update_mode(self):
        self.mode_label.configure(text=f"Mode: {self.mode.get()}")

    def draw_block(self, block_object):
        for shape_id in block_object.data['shape_ids']:
            self.grid_canvas.delete(shape_id)
        block_object.data['shape_ids'] = []

        if block_object.data['cell_name'] == "TSV":
            llx = block_object.llx_in_canvas*self.cell_size
            lly = block_object.lly_in_canvas*self.cell_size
            urx = (block_object.urx_in_canvas+1)*self.cell_size
            ury = (block_object.ury_in_canvas+1)*self.cell_size
            if block_object in self.selected_blocks:
                color = darken_color(self.SHAPE_COLORS[block_object.data['cell_name']], 0.5)
            else:
                color = self.SHAPE_COLORS[block_object.data['cell_name']]
            block_object.data['shape_ids'].append(self.grid_canvas.create_oval(llx, ury, urx, lly, fill=color, outline=''))
            for dx, dy in block_object.block_shape:
                grid_x, grid_y = block_object.data['x'] + dx, block_object.data['y'] + dy
                self.grid_state[grid_x][grid_y] = id(block_object)
        else:
            if block_object in self.selected_blocks:
                color = darken_color(self.SHAPE_COLORS[block_object.data['cell_name']], 0.5)
            else:
                color = self.SHAPE_COLORS[block_object.data['cell_name']]

            llx = block_object.llx_in_canvas*self.cell_size
            lly = block_object.lly_in_canvas*self.cell_size
            urx = (block_object.urx_in_canvas+1)*self.cell_size
            ury = (block_object.ury_in_canvas+1)*self.cell_size

            obj_id = self.grid_canvas.create_rectangle(llx, lly, urx, ury, fill=color, outline='')
            block_object.data['shape_ids'].append(obj_id)

            for dx, dy in block_object.block_shape:
                grid_x, grid_y = block_object.data['x'] + dx, block_object.data['y'] + dy
                self.grid_state[grid_x][grid_y] = id(block_object)

            # Show block name
            min_x = min(dx for dx, dy in block_object.block_shape)
            min_y = min(dy for dx, dy in block_object.block_shape)
            max_x = max(dx for dx, dy in block_object.block_shape)
            max_y = max(dy for dx, dy in block_object.block_shape)
            center_x = (min_x + max_x + 1) * self.cell_size // 2
            center_y = (min_y + max_y + 1) * self.cell_size // 2
            if block_object.data['cell_name'] != 'Blockage' and block_object.data['cell_name'] != 'GPIO':
                #obj_id = self.grid_canvas.create_text(block_object.data['x']*self.cell_size + center_x, (block_object.data['y']-3.5)*self.cell_size + center_y, text=block_object.data['cell_name'].split('_')[0], font=("Arial", 8))
                if "FCCC_ARRAY_" in block_object.data['cell_name']:
                    name = block_object.data['cell_name'][11:]
                elif "CPU_LITE_ARRAY_" in block_object.data['cell_name']:
                    name = block_object.data['cell_name'][15:]
                elif "CPU2_ARRAY_" in block_object.data['cell_name']:
                    name = block_object.data['cell_name'][11:]
                elif "SRAM_ARRAY_" in block_object.data['cell_name']:
                    name = block_object.data['cell_name'][11:]
                elif "ISP_ARRAY_" in block_object.data['cell_name']:
                    name = block_object.data['cell_name'][10:]
                else:
                    name = block_object.data['cell_name'].split('_')[0]
                obj_id = self.grid_canvas.create_text(block_object.data['x']*self.cell_size + center_x, (block_object.data['y']-3.5)*self.cell_size + center_y, text=name, font=("Arial", 8))
                block_object.data['shape_ids'].append(obj_id)
                obj_id = self.grid_canvas.create_text(block_object.data['x']*self.cell_size + center_x, (block_object.data['y']+3.5)*self.cell_size + center_y, text=block_object.data['orientation'], font=("Arial", 8))
                block_object.data['shape_ids'].append(obj_id)

            outline_width = 3
            if block_object.data['orientation'] == 'R0':
                if 'T' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(llx, lly, urx, lly, width=outline_width))
                if 'B' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(llx, ury, urx, ury, width=outline_width))
                if 'L' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(llx, lly, llx, ury, width=outline_width))
                if 'R' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(urx, lly, urx, ury, width=outline_width))
            elif block_object.data['orientation'] == 'MX':
                if 'B' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(llx, lly, urx, lly, width=outline_width))
                if 'T' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(llx, ury, urx, ury, width=outline_width))
                if 'L' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(llx, lly, llx, ury, width=outline_width))
                if 'R' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(urx, lly, urx, ury, width=outline_width))
            elif block_object.data['orientation'] == 'MY':
                if 'T' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(llx, lly, urx, lly, width=outline_width))
                if 'B' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(llx, ury, urx, ury, width=outline_width))
                if 'R' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(llx, lly, llx, ury, width=outline_width))
                if 'L' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(urx, lly, urx, ury, width=outline_width))
            elif block_object.data['orientation'] == 'R180':
                if 'B' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(llx, lly, urx, lly, width=outline_width))
                if 'T' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(llx, ury, urx, ury, width=outline_width))
                if 'R' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(llx, lly, llx, ury, width=outline_width))
                if 'L' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(urx, lly, urx, ury, width=outline_width))
            #elif block_object.data['orientation'] == 'R90':
            #    if 'T' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(llx, lly, llx, ury, width=outline_width))
            #    if 'B' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(urx, lly, urx, ury, width=outline_width))
            #    if 'L' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(llx, lly, urx, lly, width=outline_width))
            #    if 'R' in self.SHAPE_PINSIDES[block_object.data['cell_name']]: block_object.data['shape_ids'].append(self.grid_canvas.create_line(llx, ury, urx, ury, width=outline_width))

    def draw_grid(self):
        self.grid_canvas.delete("all")
        line_width = 0.1

        color = 'lightgray'

        for i in range(0, self.GRID_WIDTH + 1, 1):
            self.grid_canvas.create_line(i * self.cell_size, 0, i * self.cell_size, self.canvas_height, fill=color, width=line_width)
        for j in range(0, self.GRID_HEIGHT + 1, 1):
            self.grid_canvas.create_line(0, j * self.cell_size, self.canvas_width, j * self.cell_size, fill=color, width=line_width)

        if self.GRID_WIDTH <= 10 and self.GRID_HEIGHT <= 10: return

        interval = 10 if self.cell_size > 5 else 20
        color = "red" if self.cell_size > 5 else "gray"

        for i in range(0, self.GRID_WIDTH, interval):
            self.grid_canvas.create_line(i*self.cell_size, 0, i*self.cell_size, self.canvas_height, fill=color, width=line_width)
        for j in range(0, self.GRID_HEIGHT, interval):
            self.grid_canvas.create_line(0, j*self.cell_size, self.canvas_width, j*self.cell_size, fill=color, width=line_width)

        color = 'dimgray'
        #for i in range(0, self.GRID_WIDTH, 50):
        #    self.grid_canvas.create_line(i*self.cell_size, 0, i*self.cell_size, self.canvas_height, fill=color, width=line_width)
        #for j in range(0, self.GRID_HEIGHT, 50):
        #    self.grid_canvas.create_line(0, j*self.cell_size, self.canvas_width, j*self.cell_size, fill=color, width=line_width)

    def draw(self):
        self.draw_grid()
        for block_id, block_object in self.block_objects.items():
            self.draw_block(block_object)
        self.draw_guide_line()

    def load_from_file(self, default):
        if default == True:
            filename = self.result_dir+'/'+self.DESIGN_NAME+"_placement.json"
        else:
            filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        try:
            with open(filename, "r") as file:
                restored_database = json.loads(file.read())
                self.draw_grid()
                self.grid_state = [[None for _ in range(self.GRID_HEIGHT)] for _ in range(self.GRID_WIDTH)]
                self.block_objects = {}
                self.selected_blocks = {}
                # To prevent blockage shapes cover text 
                for k, v in restored_database.items():
                    if v['cell_name'] == 'Blockage':
                        block_object = BlockObject(v['cell_name'], v['x'], v['y'], self.SHAPE_BUTTONS[v['cell_name']], v['orientation'])
                        self.draw_block(block_object)
                        self.block_objects[id(block_object)] = block_object

                for k, v in restored_database.items():
                    if v['cell_name'] != 'Blockage':
                        block_object = BlockObject(v['cell_name'], v['x'], v['y'], self.SHAPE_BUTTONS[v['cell_name']], v['orientation'])
                        self.draw_block(block_object)
                        self.block_objects[id(block_object)] = block_object

            messagebox.showinfo("Load", f"Clean up. {len(restored_database)} blocks loaded from file successfully.")
        except FileNotFoundError:
            messagebox.showwarning("Load Error", f"Could not find the file '{filename}'. Please make sure the file exists.")

    def clear_fp(self):
        confirm = messagebox.askyesno("Clear Floorplan", f"Would you like to clear the floorplan?")
        if not confirm: return
        self.draw_grid()
        self.block_objects = {}
        self.selected_blocks = {}
        self.grid_state = [[None for _ in range(self.GRID_HEIGHT)] for _ in range(self.GRID_WIDTH)]

    def save_to_file(self):
        filename = self.result_dir+'/'+self.DESIGN_NAME+"_placement.json"
        if os.path.isfile(filename):
            confirm = messagebox.askyesno("Delete File", f"File '{filename}' exists. Would you like to overwrite it?")
            if confirm:
                os.remove(filename)
                messagebox.showinfo("Delete File", f"File '{filename}' has been overwritten.")
            else:
                messagebox.showinfo("Delete File", "File was not deleted. Saving file failed.")
                return

        with open(filename, "w") as file:
            saved_db = {}
            for k, v in self.block_objects.items():
                saved_db[k] = v.data
            file.write(json.dumps(saved_db))
        messagebox.showinfo("Save", "Placement saved to file successfully.")
        self.save_txt()

    def save_txt(self):
        filename = self.result_dir+'/'+self.DESIGN_NAME+"_grid.txt"
        with open(filename, "w") as file:
            for i in range(self.GRID_HEIGHT):
                for j in range(self.GRID_WIDTH):
                    if self.grid_state[j][i] == None:
                        file.write('None , ')
                    else:
                        name = self.block_objects[self.grid_state[j][i]].data['cell_name']
                        block_id = str(id(self.block_objects[self.grid_state[j][i]]))
                        orientation = self.block_objects[self.grid_state[j][i]].data['orientation']
                        file.write(name + '(' + block_id + ') ' + orientation + ' , ')
                file.write('\n')

if __name__ == "__main__":
    arg_dict = read_args()
    project_name = arg_dict['project_name']
    filename = f"input/{project_name}/{project_name}.csv"
    designs = read_project_config(filename)
    log.set_log_config("./pixel_drawing.log")
    log.logger.info(f"Reading project spec. form {filename}")

    for design in designs:
        placement = BlockPlacement(project_name, design['design_name'], design['grid_width'], design['grid_height'])
        placement.mainloop()


