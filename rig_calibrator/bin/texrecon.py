#!/usr/bin/env python

# Copyright (c) 2021, United States Government, as represented by the
# Administrator of the National Aeronautics and Space Administration.
#
# All rights reserved.
#
# The "ISAAC - Integrated System for Autonomous and Adaptive Caretaking
# platform" software is licensed under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with the
# License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""
A wrapper around the tools that when run together produce a textured mesh.
"""
import argparse, os, re, shutil, subprocess, sys, glob
import numpy as np

def process_args(args):
    """
    Set up the parser and parse the args.
    """

    parser = argparse.ArgumentParser(description = "Parameters for texrecon.")
    
    parser.add_argument("--rig_config",  dest="rig_config", default="",
                        help = "Rig configuration file.")
    
    parser.add_argument("--rig_sensor", dest="rig_sensor", default="",
                        help="Which rig sensor images to texture. Must be among the " + \
                        "sensors specified via --rig_config.")

    parser.add_argument("--image_list", dest="image_list",
                        default="", help= "Read images and camera poses from this list.")

    parser.add_argument("--mesh", dest="mesh",
                        default="", help="The mesh to use for texturing, in .ply format.")
    
    parser.add_argument("--out_dir", dest="out_dir",
                        default="", help="The directory where to write the textured mesh " + \
                        "and other data.")
    
    # Note how the percent sign below is escaped, by writing: %%
    parser.add_argument("--undistorted_crop_win", dest="undistorted_crop_win", default = "",
                        help = "The dimensions of the central image region to keep after "   + \
                        "undistorting an image and before uisng it in texturing. Normally "  + \
                        "85%% - 90%% of distorted (actual) image dimensions would do. "      + \
                        "This would need revisiting. Suggested the Astrobee images: "        + \
                        "sci_cam: '1250 1000' nav_cam: '1100 776'. haz_cam: '250 200'.")
    
    args = parser.parse_args()

    return args

def sanity_checks(args):

    if args.image_list == "":
        raise Exception("The path to the list having input images and poses was not specified.")

    if args.mesh == "":
        raise Exception("The mesh to use for texturing was not specified.")

    if args.rig_config == "":
        raise Exception("The path to the rig configuration was not specified.")

    if args.rig_sensor == "":
        raise Exception("The rig sensor to use for texturing was not specified.")

    if args.out_dir == "":
        raise Exception("The path to the output directory was not specified.")

    if args.undistorted_crop_win == "":
        raise Exception("The undistorted crop win was not specified.")
        
def mkdir_p(path):
    if path == "":
        return  # this can happen when path is os.path.dirname("myfile.txt")
    try:
        os.makedirs(path)
    except OSError:
        if os.path.isdir(path):
            pass
        else:
            raise Exception("Could not make directory " + path + \
                            " as a file with this name exists.")

def format_cmd(cmd):
    """If some command arguments have spaces, quote them. Then concatenate the results."""
    ans = ""
    for val in cmd:
        if " " in val or "\t" in cmd:
            val = '"' + val + '"'
        ans += val + " "
    return ans

def run_cmd(cmd, log_file, verbose=False):
    """
    Run a command and write the output to a file. In verbose mode also print to screen.
    """

    cmd_str = format_cmd(cmd)
    print(cmd_str + "\n")

    with open(log_file, "w") as f:
        f.write(cmd_str + "\n")

    process = subprocess.Popen(cmd)

    process.wait()
    if process.returncode != 0:
        print("Failed execution of: " + " ".join(cmd))
        sys.exit(1)

def parse_images_and_camera_poses(image_list, rig_sensor):

    with open(image_list, 'r') as f:
        lines = f.readlines()

    images = []
    world_to_cam = []
    for line in lines:
        m = re.match("^(.*?)\#", line)
        if m:
            # Wipe comments
            line = m.group(1)
        line = line.rstrip()
        if len(line) == 0:
            continue
        
        vals = line.split()
        if len(vals) < 13:
            raise Exception("Could not parse: " + image_list)

        image = vals[0]
        vals = vals[1:13]

        curr_sensor = os.path.basename(os.path.dirname(image))
        if curr_sensor != rig_sensor:
            continue

        # Put the values in a matrix
        M = np.ones((4,4))
        count = 0
        # Read rotation
        for row in range(3):
            for col in range(3):
                M[row][col] = float(vals[count])
                count = count + 1
        # Read translation
        for row in range(3):
            M[row][3] = float(vals[count])
            count = count + 1

        images.append(image)
        world_to_cam.append(M)
        
    return (images, world_to_cam)

def undistort_images(args, images, base_dir):

    # Form the list of distorted images
    dist_image_list = args.out_dir + "/" + args.rig_sensor + "/distorted_index.txt"
    mkdir_p(os.path.dirname(dist_image_list))
    print("Writing: " + dist_image_list)
    dist_images = []
    with open(dist_image_list, 'w') as f:
        for image in images:
            dist_images.append(image)
            f.write(image + "\n")

    # Form the list of unundistorted images
    undist_dir = args.out_dir + "/" + args.rig_sensor + "/undistorted_images"

    if os.path.isdir(undist_dir):
        # Wipe the existing directory, as it may have stray files
        print("Removing recursively old directory: " + undist_dir)
        shutil.rmtree(undist_dir)
    
    undist_image_list = args.out_dir + "/" + args.rig_sensor + "/undistorted_index.txt"
    mkdir_p(undist_dir)
    print("Writing: " + undist_image_list)
    undistorted_images = []
    with open(undist_image_list, 'w') as f:
        for image in dist_images:
            image = undist_dir + "/" + os.path.basename(image)
            # Convert to jpg, as that is what texrecon wants
            path, ext = os.path.splitext(image)
            image = path + ".jpg" 
            undistorted_images.append(image)
            f.write(image + "\n")

    undist_intrinsics = undist_dir + "/undistorted_intrinsics.txt"
    cmd = [base_dir + "/bin/undistort_image_texrecon",
           "--save_bgr",
           "--image_list", dist_image_list,
           "--output_list", undist_image_list,
           "--rig_config", args.rig_config,
           "--rig_sensor", args.rig_sensor,
           "--undistorted_crop_win", args.undistorted_crop_win,
           "--undistorted_intrinsics", undist_intrinsics]

    log_file = os.path.join(args.out_dir, "undist_" + args.rig_sensor + "_log.txt")
    print("Undistorting " + args.rig_sensor + " images. Writing the output log to: " + log_file)
    verbose = True
    run_cmd(cmd, log_file, verbose)

    return (undist_intrinsics, undistorted_images, undist_dir)

def convert_intrinsics_to_texrecon(undist_intrinsics):

    nf = -1 
    if not os.path.exists(undist_intrinsics):
        raise Exception("Missing file: " + undist_intrinsics)
        
    with open(undist_intrinsics, "r") as f:
        for line in f:
            if re.match("^\s*\#", line):
                continue  # ignore the comments
            vals = line.split()
            if len(vals) < 5:
                print("Expecting 5 parameters in " + undist_intrinsics)
                sys.exit(1)
            widx = float(vals[0])
            widy = float(vals[1])
            f = float(vals[2])
            cx = float(vals[3])
            cy = float(vals[4])

            max_wid = widx
            if widy > max_wid:
                max_wid = widy

            # normalize
            nf = f / max_wid
            ncx = cx / widx
            ncy = cy / widy
            d0 = 0.0
            d1 = 0.0
            paspect = 1.0
            break  # finished reading the line we care for

    if nf <= 0:
        raise Exception("Could not parse the undistorted intrinsics from: " + undist_intrinsics)
        
    return (nf, d0, d1, paspect, ncx, ncy)

def create_texrecon_cameras(undistorted_images, world_to_cam, nf, d0, d1, paspect, ncx, ncy):
    if len(undistorted_images) != len(world_to_cam):
        raise Exception("Expecting as many images as cameras.")

    for it in range(len(undistorted_images)):
        path, ext = os.path.splitext(undistorted_images[it])
        cam = path + ".cam"

        print("Writing: " + cam)
        with open(cam, "w") as g:
            M = world_to_cam[it]
            # write translation
            g.write("%0.17g %0.17g %0.17g " % (M[0][3], M[1][3], M[2][3]))

            # write rotation
            g.write(
                "%0.17g %0.17g %0.17g %0.17g %0.17g %0.17g %0.17g %0.17g %0.17g\n"
                % (M[0][0], M[0][1], M[0][2], M[1][0], M[1][1], M[1][2],
                   M[2][0], M[2][1], M[2][2]))

            # normalized inrinsics
            g.write("%0.17g %0.17g %0.17g %0.17g %0.17g %0.17g\n"
                % (nf, d0, d1, paspect, ncx, ncy))
    
def run_texrecon(base_dir, undist_dir, mesh, texture_dir):

    # That is one long path
    texrecon_path = base_dir + "/bin/texrecon"
    if not os.path.exists(texrecon_path):
        raise Exception("Cannot find: " + texrecon_path)
    
    mkdir_p(texture_dir)

    cmd = [texrecon_path, undist_dir, mesh, texture_dir,
           "-o", "gauss_clamping",
           "-d", "view_dir_dot_face_dir", # TODO(oalexan1): The -d option needs study
           "--keep_unseen_faces"]

    log_file = os.path.join(texture_dir, "texrecon_log.txt")
    print("Running texrecon. Writing the output log to: " + log_file + ".\n")

    run_cmd(cmd, log_file, verbose = True)

    textured_mesh = texture_dir + ".obj"

    print("Wrote: " + textured_mesh)
    
    return textured_mesh

if __name__ == "__main__":

    args = process_args(sys.argv)

    sanity_checks(args)

    mkdir_p(args.out_dir)

    (images, world_to_cam) = parse_images_and_camera_poses(args.image_list, args.rig_sensor)
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[0])))
    (undist_intrinsics, undistorted_images, undist_dir) = undistort_images(args, images, base_dir)

    (nf, d0, d1, paspect, ncx, ncy) = convert_intrinsics_to_texrecon(undist_intrinsics)

    create_texrecon_cameras(undistorted_images, world_to_cam, nf, d0, d1, paspect, ncx, ncy)

    texture_dir = args.out_dir + "/" + args.rig_sensor + "/texture"
    run_texrecon(base_dir, undist_dir, args.mesh, texture_dir)

