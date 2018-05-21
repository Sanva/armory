import bpy
import arm.utils
import arm.assets as assets
import arm.material.cycles as cycles
import arm.material.mat_state as mat_state
import arm.material.mat_utils as mat_utils
import arm.material.make_particle as make_particle
import arm.make_state as state

def make(context_id):
    rpdat = arm.utils.get_rp()
    if rpdat.rp_gi == 'Voxel GI':
        con = make_gi(context_id)
    else:
        con = make_ao(context_id)

    assets.vs_equal(con, assets.shader_cons['voxel_vert'])
    assets.gs_equal(con, assets.shader_cons['voxel_frag'])
    assets.fs_equal(con, assets.shader_cons['voxel_geom'])

    return con

def make_gi(context_id):
    con_voxel = mat_state.data.add_context({ 'name': context_id, 'depth_write': False, 'compare_mode': 'always', 'cull_mode': 'none', 'color_write_red': False, 'color_write_green': False, 'color_write_blue': False, 'color_write_alpha': False, 'conservative_raster': True })
    wrd = bpy.data.worlds['Arm']

    vert = con_voxel.make_vert()
    frag = con_voxel.make_frag()
    geom = con_voxel.make_geom()
    tesc = None
    tese = None
    geom.ins = vert.outs
    frag.ins = geom.outs

    frag.add_include('compiled.glsl')
    frag.add_include('std/math.glsl')
    frag.add_include('std/imageatomic.glsl')
    frag.add_include('std/gbuffer.glsl')
    frag.write_header('#extension GL_ARB_shader_image_load_store : enable')

    rpdat = arm.utils.get_rp()
    frag.add_uniform('layout(r32ui) uimage3D voxels')
    frag.add_uniform('layout(r32ui) uimage3D voxelsNor')

    frag.write('if (abs(voxposition.z) > ' + rpdat.rp_voxelgi_resolution_z + ' || abs(voxposition.x) > 1 || abs(voxposition.y) > 1) return;')
    frag.write('vec3 wposition = voxposition * voxelgiHalfExtents;')
    if rpdat.arm_voxelgi_revoxelize and rpdat.arm_voxelgi_camera:
        frag.add_uniform('vec3 eyeSnap', '_cameraPositionSnap')
        frag.write('wposition += eyeSnap;')

    frag.write('vec3 basecol;')
    frag.write('float roughness;') #
    frag.write('float metallic;') #
    frag.write('float occlusion;') #
    frag.write('float specular;') #
    parse_opacity = rpdat.arm_voxelgi_refraction
    if parse_opacity:
        frag.write('float opacity;')
    frag.write('float dotNV = 0.0;')
    cycles.parse(mat_state.nodes, con_voxel, vert, frag, geom, tesc, tese, parse_opacity=parse_opacity, parse_displacement=False, basecol_only=True)

    # Voxelized particles
    particle = mat_state.material.arm_particle
    if particle == 'gpu':
        # make_particle.write(vert, particle_info=cycles.particle_info)
        frag.write_pre = True
        frag.write('const float p_index = 0;')
        frag.write('const float p_age = 0;')
        frag.write('const float p_lifetime = 0;')
        frag.write('const vec3 p_location = vec3(0);')
        frag.write('const float p_size = 0;')
        frag.write('const vec3 p_velocity = vec3(0);')
        frag.write('const vec3 p_angular_velocity = vec3(0);')
        frag.write_pre = False

    if not frag.contains('vec3 n ='):
        frag.write_pre = True
        frag.write('vec3 n;')
        frag.write_pre = False

    export_mpos = frag.contains('mposition') and not frag.contains('vec3 mposition')
    if export_mpos:
        vert.add_out('vec3 mpositionGeom')
        vert.write_pre = True
        vert.write('mpositionGeom = pos;')
        vert.write_pre = False

    export_bpos = frag.contains('bposition') and not frag.contains('vec3 bposition')
    if export_bpos:
        vert.add_out('vec3 bpositionGeom')
        vert.add_uniform('vec3 dim', link='_dim')
        vert.add_uniform('vec3 hdim', link='_halfDim')
        vert.write_pre = True
        vert.write('bpositionGeom = (pos.xyz + hdim) / dim;')
        vert.write_pre = False

    vert.add_uniform('mat4 W', '_worldMatrix')
    vert.add_uniform('mat3 N', '_normalMatrix')

    vert.add_out('vec3 voxpositionGeom')
    vert.add_out('vec3 wnormalGeom')

    vert.add_include('compiled.glsl')

    if con_voxel.is_elem('col'):
        vert.add_out('vec3 vcolorGeom')
        vert.write('vcolorGeom = col;')

    if con_voxel.is_elem('tex'):
        vert.add_out('vec2 texCoordGeom')
        vert.write('texCoordGeom = tex;')

    if rpdat.arm_voxelgi_revoxelize and rpdat.arm_voxelgi_camera:
        vert.add_uniform('vec3 eyeSnap', '_cameraPositionSnap')
        vert.write('voxpositionGeom = (vec3(W * vec4(pos, 1.0)) - eyeSnap) / voxelgiHalfExtents;')
    else: 
        vert.write('voxpositionGeom = vec3(W * vec4(pos, 1.0)) / voxelgiHalfExtents;')
    vert.write('wnormalGeom = normalize(N * nor);')
    # vert.write('gl_Position = vec4(0.0, 0.0, 0.0, 1.0);')

    geom.add_out('vec3 voxposition')
    geom.add_out('vec3 wnormal')
    if con_voxel.is_elem('col'):
        geom.add_out('vec3 vcolor')
    if con_voxel.is_elem('tex'):
        geom.add_out('vec2 texCoord')
    if export_mpos:
        geom.add_out('vec3 mposition')
    if export_bpos:
        geom.add_out('vec3 bposition')

    geom.write('vec3 p1 = voxpositionGeom[1] - voxpositionGeom[0];')
    geom.write('vec3 p2 = voxpositionGeom[2] - voxpositionGeom[0];')
    geom.write('vec3 p = abs(cross(p1, p2));')
    geom.write('for (uint i = 0; i < 3; ++i) {')
    geom.write('    voxposition = voxpositionGeom[i];')
    geom.write('    wnormal = wnormalGeom[i];')
    if con_voxel.is_elem('col'):
        geom.write('    vcolor = vcolorGeom[i];')
    if con_voxel.is_elem('tex'):
        geom.write('    texCoord = texCoordGeom[i];')
    if export_mpos:
        geom.write('    mposition = mpositionGeom[i];')
    if export_bpos:
        geom.write('    bposition = bpositionGeom[i];')
    geom.write('    if (p.z > p.x && p.z > p.y) {')
    geom.write('        gl_Position = vec4(voxposition.x, voxposition.y, 0.0, 1.0);')
    geom.write('    }')
    geom.write('    else if (p.x > p.y && p.x > p.z) {')
    geom.write('        gl_Position = vec4(voxposition.y, voxposition.z, 0.0, 1.0);')
    geom.write('    }')
    geom.write('    else {')
    geom.write('        gl_Position = vec4(voxposition.x, voxposition.z, 0.0, 1.0);')
    geom.write('    }')
    geom.write('    EmitVertex();')
    geom.write('}')
    geom.write('EndPrimitive();')

    frag.write('vec3 voxel = voxposition * 0.5 + 0.5;')
    frag.write('uint val = convVec4ToRGBA8(vec4(basecol, 1.0) * 255);')
    frag.write('imageAtomicMax(voxels, ivec3(voxelgiResolution * voxel), val);')

    frag.write('val = encNor(wnormal);');
    frag.write('imageAtomicMax(voxelsNor, ivec3(voxelgiResolution * voxel), val);')
        
        # frag.write('imageStore(voxels, ivec3(voxelgiResolution * voxel), vec4(color, 1.0));')
        # frag.write('imageAtomicRGBA8Avg(voxels, ivec3(voxelgiResolution * voxel), vec4(color, 1.0));')
            
        # frag.write('ivec3 coords = ivec3(voxelgiResolution * voxel);')
        # if parse_opacity:
        #     frag.write('vec4 val = vec4(color, opacity);')
        # else:
        #     frag.write('vec4 val = vec4(color, 1.0);')
        # frag.write('val *= 255.0;')
        # frag.write('uint newVal = encUnsignedNibble(convVec4ToRGBA8(val), 1);')
        # frag.write('uint prevStoredVal = 0;')
        # frag.write('uint currStoredVal;')
        # # frag.write('int counter = 0;')
        # # frag.write('while ((currStoredVal = imageAtomicCompSwap(voxels, coords, prevStoredVal, newVal)) != prevStoredVal && counter < 16) {')
        # frag.write('while ((currStoredVal = imageAtomicCompSwap(voxels, coords, prevStoredVal, newVal)) != prevStoredVal) {')
        # frag.write('    vec4 rval = convRGBA8ToVec4(currStoredVal & 0xFEFEFEFE);')
        # frag.write('    uint n = decUnsignedNibble(currStoredVal);')
        # frag.write('    rval = rval * n + val;')
        # frag.write('    rval /= ++n;')
        # frag.write('    rval = round(rval / 2) * 2;')
        # frag.write('    newVal = encUnsignedNibble(convVec4ToRGBA8(rval), n);')
        # frag.write('    prevStoredVal = currStoredVal;')
        # # frag.write('    counter++;')
        # frag.write('}')

        # frag.write('val.rgb *= 255.0f;')
        # frag.write('uint newVal = convVec4ToRGBA8(val);')
        # frag.write('uint prevStoredVal = 0;')
        # frag.write('uint curStoredVal;')
        # frag.write('while ((curStoredVal = imageAtomicCompSwap(voxels, coords, prevStoredVal, newVal)) != prevStoredVal) {')
        # frag.write('    prevStoredVal = curStoredVal;')
        # frag.write('    vec4 rval = convRGBA8ToVec4(curStoredVal);')
        # frag.write('    rval.xyz = (rval.xyz * rval.w);')
        # frag.write('    vec4 curValF = rval + val;')
        # frag.write('    curValF.xyz /= (curValF.w);')
        # frag.write('    newVal = convVec4ToRGBA8(curValF);')
        # frag.write('}')

    return con_voxel

def make_ao(context_id):
    con_voxel = mat_state.data.add_context({ 'name': context_id, 'depth_write': False, 'compare_mode': 'always', 'cull_mode': 'none', 'color_write_red': False, 'color_write_green': False, 'color_write_blue': False, 'color_write_alpha': False, 'conservative_raster': True })
    wrd = bpy.data.worlds['Arm']

    vert = con_voxel.make_vert()
    frag = con_voxel.make_frag()
    geom = con_voxel.make_geom()
    tesc = None
    tese = None

    geom.ins = vert.outs
    frag.ins = geom.outs

    frag.add_include('compiled.glsl')
    frag.add_include('std/math.glsl')
    frag.add_include('std/imageatomic.glsl')
    frag.write_header('#extension GL_ARB_shader_image_load_store : enable')

    rpdat = arm.utils.get_rp()
    # frag.add_uniform('layout(r32ui) uimage3D voxels')
    frag.add_uniform('layout(r8) writeonly image3D voxels')

    vert.add_include('compiled.glsl')
    vert.add_uniform('mat4 W', '_worldMatrix')
    vert.add_out('vec3 voxpositionGeom')

    if rpdat.arm_voxelgi_revoxelize and rpdat.arm_voxelgi_camera:
        vert.add_uniform('vec3 eyeSnap', '_cameraPositionSnap')
        vert.write('voxpositionGeom = (vec3(W * vec4(pos, 1.0)) - eyeSnap) / voxelgiHalfExtents;')
    else: 
        vert.write('voxpositionGeom = vec3(W * vec4(pos, 1.0)) / voxelgiHalfExtents;')

    # vert.write('gl_Position = vec4(0.0, 0.0, 0.0, 1.0);')

    if False: # Maxwell
        # https://developer.nvidia.com/sites/default/files/akamai/opengl/specs/GL_NV_geometry_shader_passthrough.txt
        # https://www.khronos.org/registry/OpenGL/extensions/NV/NV_viewport_swizzle.txt
        vert.write('gl_Position = vec4(voxpositionGeom.x, voxpositionGeom.y, 0.0, 1.0);')
        geom.write_header('#extension GL_NV_geometry_shader_passthrough : require')
        geom.geom_passthrough = True
        # geom.add_out('vec3 voxposition')
        geom.write('vec3 p1 = voxpositionGeom[1] - voxpositionGeom[0];')
        geom.write('vec3 p2 = voxpositionGeom[2] - voxpositionGeom[0];')
        geom.write('vec3 n = abs(cross(p1, p2));')
        geom.write('gl_ViewportIndex = 1;')
        geom.write_header('out int gl_ViewportIndex;')
        # g4.setViewport():
        #glViewportIndexedf(0, x, _renderTargetHeight - y - height, width, height);
        #glViewportIndexedf(1, x, _renderTargetHeight - y - height, width, height);
        #glViewportSwizzleNV(1, GL_VIEWPORT_SWIZZLE_POSITIVE_X_NV, GL_VIEWPORT_SWIZZLE_POSITIVE_Y_NV, GL_VIEWPORT_SWIZZLE_POSITIVE_Z_NV, GL_VIEWPORT_SWIZZLE_POSITIVE_W_NV);
        frag.add_in('vec3 voxpositionGeom')
        frag.write('if (abs(voxpositionGeom.z) > ' + rpdat.rp_voxelgi_resolution_z + ' || abs(voxpositionGeom.x) > 1 || abs(voxpositionGeom.y) > 1) return;')
        frag.write('imageStore(voxels, ivec3(voxelgiResolution * (voxpositionGeom * 0.5 + 0.5)), vec4(1.0));')
    else:
        geom.add_out('vec3 voxposition')
        geom.write('vec3 p1 = voxpositionGeom[1] - voxpositionGeom[0];')
        geom.write('vec3 p2 = voxpositionGeom[2] - voxpositionGeom[0];')
        geom.write('vec3 p = abs(cross(p1, p2));')
        geom.write('for (uint i = 0; i < 3; ++i) {')
        geom.write('    voxposition = voxpositionGeom[i];')
        geom.write('    if (p.z > p.x && p.z > p.y) {')
        geom.write('        gl_Position = vec4(voxposition.x, voxposition.y, 0.0, 1.0);')
        geom.write('    }')
        geom.write('    else if (p.x > p.y && p.x > p.z) {')
        geom.write('        gl_Position = vec4(voxposition.y, voxposition.z, 0.0, 1.0);')
        geom.write('    }')
        geom.write('    else {')
        geom.write('        gl_Position = vec4(voxposition.x, voxposition.z, 0.0, 1.0);')
        geom.write('    }')
        geom.write('    EmitVertex();')
        geom.write('}')
        geom.write('EndPrimitive();')

        frag.write('if (abs(voxposition.z) > ' + rpdat.rp_voxelgi_resolution_z + ' || abs(voxposition.x) > 1 || abs(voxposition.y) > 1) return;')
        frag.write('imageStore(voxels, ivec3(voxelgiResolution * (voxposition * 0.5 + 0.5)), vec4(1.0));')

    return con_voxel
