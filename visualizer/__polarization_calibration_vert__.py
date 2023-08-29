#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Sep  1 12:02:25 2022

@author: nick
"""

import warnings, glob, os, sys
import xarray as xr
import numpy as np
import netCDF4 as nc
from matplotlib import pyplot as plt
from .readers.parse_pcb_args import call_parser, check_parser
from .readers.check import check_channels_no_exclude as check_channels
from .tools import normalize
from .plotting import make_axis, make_title, make_plot
from .tools.smoothing import sliding_average_1D
from .tools import average

# Ignores all warnings --> they are not printed in terminal
warnings.filterwarnings('ignore')

def main(args, __version__):
    # Check the command line argument information
    args = check_parser(args)
    
    print('-----------------------------------------')
    print('Initializing the pcb. Calibration...')
    print('-----------------------------------------')
    
    # Read the pcb cal file
    data = xr.open_dataset(args['input_file'])
    
    # Extract signal
    sig_ray = data.Range_Corrected_Signals_Rayleigh
    sig_ray = sig_ray.copy().where(sig_ray != nc.default_fillvals['f8'])
    
    sig_m45 = data.Range_Corrected_Signals_minus_45
    sig_m45 = sig_m45.copy().where(sig_m45 != nc.default_fillvals['f8'])\
        .mean(dim = 'time_m45')
    
    sig_p45 = data.Range_Corrected_Signals_plus_45
    sig_p45 = sig_p45.copy().where(sig_p45 != nc.default_fillvals['f8'])\
        .mean(dim = 'time_p45')
    
    # Extract signal time, channels, and bins
    channels = data.channel.values
    
    if args['ch_r'] == None or args['ch_t'] == None:
        channels_r = []
        channels_t = []
        ch_r_all = np.array([ch for ch in channels if ch[7] == 'r'])
        ch_t_all = np.array([ch for ch in channels if ch[7] == 't'])
        for ch_r in ch_r_all:
            for ch_t in ch_t_all:
                if ch_r[4]  == ch_t[4] and ch_r[6]  == ch_t[6] and \
                    ch_r[:4]  == ch_t[:4]:
                        channels_r.extend([ch_r])
                        channels_t.extend([ch_t])
    else:
        channels_r = args['ch_r']
        channels_t = args['ch_t']
    
    # Check if the parsed channels exist
    channels_r = check_channels(sel_channels = channels_r, all_channels = channels)
    channels_t = check_channels(sel_channels = channels_t, all_channels = channels)
    
    G_R_def = len(channels_r) * [1.]
    G_T_def = len(channels_r) * [1.]
    H_R_def = len(channels_r) * [1.]
    H_T_def = len(channels_r) * [1.]

    for i in range(len(channels_r)):
        if channels_r[i][5] == 'c':
            H_R_def[i] = -1.
        if channels_t[i][5] == 'c':
            H_T_def[i] = -1.

    # Extract pair values
    if args['K'] == None:
        K = len(channels_r) * [1.]
    else:
        K = args['K']

    if args['G_R'] == None:
        G_R = G_R_def
    else:
        G_R = args['G_R']

    if args['G_T'] == None:
        G_T = G_T_def
    else:
        G_T = args['G_T']

    if args['H_R'] == None:
        H_R = H_R_def
    else:
        H_R = args['H_R']

    if args['H_T'] == None:
        H_T = H_T_def
    else:
        H_T = args['H_T']

    if args['R_to_T_transmission_ratio'] == None:
        TR_to_TT = len(channels_r) * [1.]
    else:
        TR_to_TT = args['R_to_T_transmission_ratio']

    # Extract Molecular Depolarization Ratio and Calucalte the Atm. Parameter alpha
    mldr = data.Molecular_Linear_Depolarization_Ratio
    a_m = (1. - mldr) / (1. + mldr)
    
    # Iterate over the channels
    for i in range(len(channels_r)):
                
        ch_r = channels_r[i]
        ch_t = channels_t[i]
        K_ch = K[i]
        G_R_ch = G_R[i]
        G_T_ch = G_T[i]
        H_R_ch = H_R[i]
        H_T_ch = H_T[i]
        G_R_def_ch = G_R_def[i]
        G_T_def_ch = G_T_def[i]
        H_R_def_ch = H_R_def[i]
        H_T_def_ch = H_T_def[i]
        TR_to_TT_ch = TR_to_TT[i]
        
        print(f"-- channels: {ch_r} & {ch_t}")

        ch_r_d = dict(channel = ch_r)
        ch_t_d = dict(channel = ch_t)
        
        sig_r_p45_ch = sig_p45.copy().loc[ch_r_d].values
        sig_t_p45_ch = sig_p45.copy().loc[ch_t_d].values
        sig_r_m45_ch = sig_m45.copy().loc[ch_r_d].values
        sig_t_m45_ch = sig_m45.copy().loc[ch_t_d].values
        sig_r_ray_ch = sig_ray.copy().loc[ch_r_d].values
        sig_t_ray_ch = sig_ray.copy().loc[ch_t_d].values
        
        a_m_ch = a_m.loc[ch_r_d].values
    
        # Create the y axis (height/range)
        y_lbin_cal, y_ubin_cal, y_llim_cal, y_ulim_cal, y_vals_cal, y_label_cal = \
            make_axis.polarization_calibration_y(
                heights = data.Height_levels_Calibration.loc[ch_r_d].values, 
                ranges = data.Range_levels_Calibration.loc[ch_r_d].values,
                y_lims = args['y_lims_calibration'], 
                use_dis = args['use_range'])
    
        # Create the y axis (height/range)
        y_lbin_ray, y_ubin_ray, y_llim_ray, y_ulim_ray, y_vals_ray, y_label_ray = \
            make_axis.polarization_calibration_y(
                heights = data.Height_levels_Rayleigh.loc[ch_r_d].values, 
                ranges = data.Range_levels_Rayleigh.loc[ch_r_d].values,
                y_lims = args['y_lims_rayleigh'], 
                use_dis = args['use_range'])
    
        # Smoothing
        x_r_m45_sm, _ = \
            sliding_average_1D(y_vals = sig_r_m45_ch, 
                               x_vals = y_vals_cal,
                               x_sm_lims = args['smoothing_range'],
                               x_sm_hwin = args['half_window'],
                               expo = args['smooth_exponential'])

        x_t_m45_sm, _ = \
            sliding_average_1D(y_vals = sig_t_m45_ch, 
                               x_vals = y_vals_cal,
                               x_sm_lims = args['smoothing_range'],
                               x_sm_hwin = args['half_window'],
                               expo = args['smooth_exponential'])
            
        x_r_p45_sm, _ = \
            sliding_average_1D(y_vals = sig_r_p45_ch, 
                               x_vals = y_vals_cal,
                               x_sm_lims = args['smoothing_range'],
                               x_sm_hwin = args['half_window'],
                               expo = args['smooth_exponential'])

        x_t_p45_sm, _ = \
            sliding_average_1D(y_vals = sig_t_p45_ch, 
                               x_vals = y_vals_cal,
                               x_sm_lims = args['smoothing_range'],
                               x_sm_hwin = args['half_window'],
                               expo = args['smooth_exponential'])

        x_r_ray_sm, _ = \
            sliding_average_1D(y_vals = sig_r_ray_ch, 
                               x_vals = y_vals_ray,
                               x_sm_lims = args['smoothing_range'],
                               x_sm_hwin = args['half_window'],
                               expo = args['smooth_exponential'])    
            
        x_t_ray_sm, _ = \
            sliding_average_1D(y_vals = sig_t_ray_ch, 
                               x_vals = y_vals_ray,
                               x_sm_lims = args['smoothing_range'],
                               x_sm_hwin = args['half_window'],
                               expo = args['smooth_exponential'])      
        
        avg_r_m45 = average.region(sig = sig_r_m45_ch, 
                                   x_vals = y_vals_cal, 
                                   calibr = args['calibration_height'], 
                                   hwin = args['half_calibration_window'], 
                                   axis = 0,
                                   squeeze = True)
        
        avg_t_m45 = average.region(sig = sig_t_m45_ch, 
                                   x_vals = y_vals_cal, 
                                   calibr = args['calibration_height'], 
                                   hwin = args['half_calibration_window'], 
                                   axis = 0,
                                   squeeze = True)
        
        avg_r_p45 = average.region(sig = sig_r_p45_ch, 
                                   x_vals = y_vals_cal, 
                                   calibr = args['calibration_height'], 
                                   hwin = args['half_calibration_window'], 
                                   axis = 0,
                                   squeeze = True)
        
        avg_t_p45 = average.region(sig = sig_t_p45_ch, 
                                   x_vals = y_vals_cal, 
                                   calibr = args['calibration_height'], 
                                   hwin = args['half_calibration_window'], 
                                   axis = 0,
                                   squeeze = True)
        
        avg_r_ray = average.region(sig = sig_r_ray_ch, 
                                   x_vals = y_vals_ray, 
                                   calibr = args['rayleigh_height'], 
                                   hwin = args['half_rayleigh_window'], 
                                   axis = 0,
                                   squeeze = True)
        
        avg_t_ray = average.region(sig = sig_t_ray_ch, 
                                   x_vals = y_vals_ray, 
                                   calibr = args['rayleigh_height'], 
                                   hwin = args['half_rayleigh_window'], 
                                   axis = 0,
                                   squeeze = True)

        avg_a_m_ch = average.region(sig = a_m_ch, 
                                    x_vals = y_vals_ray, 
                                    calibr = args['rayleigh_height'], 
                                    hwin = args['half_rayleigh_window'], 
                                    axis = 0,
                                    squeeze = True) 
                
        eta_m45_prf = (x_r_m45_sm / x_t_m45_sm) 
    
        eta_p45_prf = (x_r_p45_sm / x_t_p45_sm)
        
        eta_prf = np.sqrt(eta_m45_prf * eta_p45_prf)
        
        eta_f_s_m45 = (avg_r_m45 / avg_t_m45)
    
        eta_f_s_p45 = (avg_r_p45 / avg_t_p45)
        
        eta_f_s = np.sqrt(eta_f_s_p45 * eta_f_s_m45)
        
        eta_s = eta_f_s / TR_to_TT_ch

        eta = eta_s / K_ch
        
        delta_s_prf = (x_r_ray_sm / x_t_ray_sm) / eta

        delta_s = (avg_r_ray / avg_t_ray) / eta

        delta_c_prf = (delta_s_prf * (G_T_ch + H_T_ch) - (G_R_ch + H_R_ch)) /\
            ((G_R_ch - H_R_ch) - delta_s_prf * (G_T_ch - H_T_ch))
        
        delta_c = (delta_s * (G_T_def_ch+ H_T_def_ch) - (G_R_def_ch + H_R_def_ch)) /\
            ((G_R_def_ch - H_R_def_ch) - delta_s * (G_T_def_ch - H_T_def_ch))

        delta_prf = (delta_s_prf * (G_T_ch + H_T_ch) - (G_R_ch + H_R_ch)) /\
            ((G_R_ch - H_R_ch) - delta_s_prf * (G_T_ch - H_T_ch))

        delta = (delta_s * (G_T_ch + H_T_ch) - (G_R_ch + H_R_ch)) /\
            ((G_R_ch - H_R_ch) - delta_s * (G_T_ch - H_T_ch))
        
        delta_m_prf = (1. - a_m_ch) / (1. + a_m_ch)
        
        delta_m = (1. - avg_a_m_ch) / (1. + avg_a_m_ch)
            
        psi = (eta_f_s_p45 - eta_f_s_m45) / (eta_f_s_p45 + eta_f_s_m45)
        
        kappa = 1.
        
        epsilon = np.rad2deg(0.5 * np.arcsin(np.tan(0.5 * np.arcsin(psi) / kappa)))
        # kappa = np.tan(0.5 * np.arcsin(psi)) / np.sin(2. * np.deg2rad(epsilon)) 
    
            
        # Create the x axis (calibration)
        x_llim_cal, x_ulim_cal, x_label_cal = \
            make_axis.polarization_calibration_cal_x(
                ratio_m = eta_f_s_m45, ratio_p = eta_f_s_p45,
                x_lims_cal = args['x_lims_calibration'])
            
        # Create the x axis (rayleigh)
        x_llim_ray, x_ulim_ray, x_label_ray = \
            make_axis.polarization_calibration_ray_x(
                ratio = delta_s, x_lims_ray = args['x_lims_rayleigh'])
        
                
        # Make title
        title = make_title.polarization_calibration(
                start_date_cal = data.RawData_Start_Date_Calibration,
                start_time_cal = data.RawData_Start_Time_UT_Calibration, 
                end_time_cal = data.RawData_Stop_Time_UT_Calibration,
                start_date_ray = data.RawData_Start_Date_Rayleigh,
                start_time_ray = data.RawData_Start_Time_UT_Rayleigh, 
                end_time_ray = data.RawData_Stop_Time_UT_Rayleigh,
                lidar = data.Lidar_Name_Calibration, 
                channel_r = ch_r, 
                channel_t = ch_t, 
                zan = data.Laser_Pointing_Angle_Calibration,
                lat = data.Latitude_degrees_north_Calibration, 
                lon = data.Longitude_degrees_east_Calibration, 
                elv = data.Altitude_meter_asl_Calibration)
        
       
        # Make filename
        fname = f'{data.Measurement_ID_Calibration}_{data.Lidar_Name_Calibration}_pcb_{ch_r}_to_{ch_t}_ATLAS_{__version__}.png'

        fpath = \
            make_plot.polarization_calibration(dir_out = args['output_folder'], 
                                               fname = fname, title = title,
                                               dpi_val = args['dpi'],
                                               y_cal = args['calibration_height'],
                                               cal_hwin = args['half_calibration_window'],
                                               y_vdr = args['rayleigh_height'],
                                               vdr_hwin = args['half_rayleigh_window'],
                                               y_vals_cal = y_vals_cal, 
                                               y_vals_vdr = y_vals_ray, 
                                               x1_vals = eta_prf, 
                                               x2_vals = eta_p45_prf, 
                                               x3_vals = eta_m45_prf, 
                                               x4_vals = delta_c_prf,
                                               x5_vals = delta_prf,
                                               x6_vals = delta_m_prf,
                                               eta = eta, eta_f_s = eta_f_s, 
                                               eta_s = eta_s, 
                                               delta_m = delta_m,
                                               delta_c = delta_c,
                                               delta = delta,
                                               epsilon = epsilon,
                                               y_lbin_cal = y_lbin_cal,
                                               y_ubin_cal = y_ubin_cal, 
                                               y_llim_cal = y_llim_cal,
                                               y_ulim_cal = y_ulim_cal, 
                                               x_llim_cal = x_llim_cal, 
                                               x_ulim_cal = x_ulim_cal, 
                                               y_lbin_vdr = y_lbin_ray, 
                                               y_ubin_vdr = y_ubin_ray, 
                                               y_llim_vdr = y_llim_ray, 
                                               y_ulim_vdr = y_ulim_ray, 
                                               x_llim_vdr = x_llim_ray, 
                                               x_ulim_vdr = x_ulim_ray, 
                                               x_label_cal = x_label_cal, 
                                               y_label_cal = y_label_cal, 
                                               y_tick_cal = args['y_tick_calibration'],
                                               x_label_vdr = x_label_ray, 
                                               y_label_vdr = y_label_ray, 
                                               y_tick_vdr = args['y_tick_rayleigh'])  
            
    print('-----------------------------------------')
    print(' ')
    
    return()

if __name__ == '__main__':
    
    sys.path.append('../')
    
    from version import __version__
    
    # Get the command line argument information
    args = call_parser()
    
    # Call main
    main(args, __version__)
    
    # sys.exit()
    # # Add metadata to the quicklook plot
    # from PIL import Image
    # from PIL import PngImagePlugin
   
    # METADATA = {"processing_software" : f"ATLAS_{data.version}",
    #             "measurement_id" : f"{data.Measurement_ID}",
    #             "channel" : f"{ch}",
    #             "smooth" : f"{args['smooth']}",
    #             "smoothing_exponential" : f"{args['smooth_exponential']}",
    #             "smoothing_range (lower)" : f"{args['smoothing_range'][0]}",
    #             "smoothing_range (upper)" : f"{args['smoothing_range'][-1]}",
    #             "half_window (lower)": f"{args['half_window'][0]}",
    #             "half_window (upper)": f"{args['half_window'][-1]}",
    #             "dpi" : f"{args['dpi']}",
    #             "use_log_scale" : f"{args['use_log_scale']}",
    #             "use_range" : f"{args['use_range']}",
    #             "x_lims (lower)" : f"{x_llim}",
    #             "x_lims (upper)" : f"{x_ulim}",
    #             "y_lims (lower)" : f"{y_vals[y_llim]}",
    #             "y_lims (upper)" : f"{y_vals[y_ulim]}",
    #             "z_lims (lower)" : f"{z_llim}",
    #             "z_lims (upper)" : f"{z_ulim}",
    #             "x_tick" : f"{x_tick}",
    #             "y_tick" : f"{args['y_tick']}"}
            
    # im = Image.open(fpath)
    # meta = PngImagePlugin.PngInfo()

    # for x in METADATA.keys():
    #     meta.add_text(x, METADATA[x])
        
    # im.save(fpath, "png", pnginfo = meta)
