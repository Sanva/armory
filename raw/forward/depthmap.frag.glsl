#version 450

#ifdef GL_ES
precision mediump float;
#endif

#ifdef _NMTex
#define _AMTex
#endif

in vec4 position;

void main() {
    float depth = position.z / position.w;	
	gl_FragColor = vec4(depth, 0.0, 0.0, 1.0);
}
